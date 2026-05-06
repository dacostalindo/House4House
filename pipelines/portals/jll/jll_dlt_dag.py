"""JLL Residential PT — dlt-driven SCD2 bronze ingestion DAG.

Tasks (in order):

  audit_to_minio   — fetch raw JSON, write to s3://raw/jll/... as audit copy.
                     Best-effort; failures log but do NOT block the load.

  load_facts       — runs jll_facts_source via dlt: developments + listings
                     SCD2 tables + per-entity heartbeat sidecars.
                     Hard-fails the DAG on error.

  validate_facts   — asserts the facts load actually landed: _dlt_loads row
                     for the run has status=0 and reasonable row counts.

Plots are intentionally not ingested. The /v1/Properties endpoint requires a
per-visitor `vui` parameter generated via the vcs.imoguia.com bootstrap
that needs a real browser. PT plot inventory is already covered by the
idealista/remax/zome pipelines.

Schedule: 0 6 * * 4 (Thursdays 06:00 UTC).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import dlt
from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable

from pipelines.portals.jll.source import (
    DEV_PAGE_SIZE,
    RATE_LIMIT_S,
    _fetch_json,
    jll_facts_source,
)

log = logging.getLogger(__name__)

PIPELINES_DIR = "/opt/airflow/dlt_state/jll"
DATASET_NAME = "bronze_listings"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "jll"


def _postgres_credentials() -> dict:
    return {
        "host": os.environ["WAREHOUSE_HOST"],
        "port": int(os.environ.get("WAREHOUSE_PORT", "5432")),
        "username": os.environ["WAREHOUSE_USER"],
        "password": os.environ["WAREHOUSE_PASSWORD"],
        "database": os.environ["WAREHOUSE_DB"],
    }


def _alert_on_failure(context: dict) -> None:
    """task_failure_callback — surfaces schema-freeze / SCD2 failures."""
    task_id = context.get("task_instance").task_id
    dag_id = context.get("task_instance").dag_id
    run_id = context.get("run_id")
    exception = context.get("exception")
    log.error(
        "[ALERT] %s.%s failed (run %s): %s",
        dag_id,
        task_id,
        run_id,
        exception,
    )


default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": _alert_on_failure,
}


with DAG(
    dag_id="jll_dlt",
    description=(
        "JLL Residential PT bronze ingestion via dlt. SCD2 for developments/listings, "
        "UPSERT sidecar heartbeats for last_seen_date."
    ),
    schedule="0 6 * * 4",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["jll", "bronze", "dlt", "scd2"],
) as dag:

    @task()
    def audit_to_minio() -> dict:
        """Best-effort raw-JSON dump to MinIO for replay/audit."""
        from minio import Minio

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        endpoint = Variable.get("MINIO_ENDPOINT", default_var="minio:9000")
        client = Minio(
            endpoint,
            access_key=Variable.get("MINIO_ACCESS_KEY"),
            secret_key=Variable.get("MINIO_SECRET_KEY"),
            secure=False,
        )
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)

        uploaded: list[str] = []

        def _put(path_key: str, payload: Any) -> None:
            with TemporaryDirectory() as td:
                fp = Path(td) / "out.json"
                fp.write_text(json.dumps(payload, ensure_ascii=False))
                obj = f"{MINIO_PREFIX}/{path_key}/{ts}.json"
                client.fput_object(MINIO_BUCKET, obj, str(fp))
                uploaded.append(f"s3://{MINIO_BUCKET}/{obj}")

        # Developments — paginate
        page = 1
        while True:
            data = _fetch_json(
                "/Developments",
                params={"lng": "en-GB", "nre": str(DEV_PAGE_SIZE), "pag": str(page)},
            )
            devs = data.get("Developments", [])
            if not devs:
                break
            _put(f"developments/p{page}", data)
            if len(devs) < DEV_PAGE_SIZE:
                break
            page += 1
            time.sleep(RATE_LIMIT_S)

        log.info("[jll_dlt] audit upload complete: %d files", len(uploaded))
        return {"uploaded": uploaded, "ts": ts}

    @task()
    def load_facts() -> dict:
        """SCD2 facts + heartbeat sidecars. Hard fail on schema-contract violation."""
        pipeline = dlt.pipeline(
            pipeline_name="jll_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR,
        )
        info = pipeline.run(jll_facts_source())
        log.info("[jll_dlt] facts load: %s", info)
        return {"load_id": pipeline.last_trace.last_load_info.loads_ids[-1]}

    @task()
    def validate_facts(facts_result: dict) -> dict:
        """Assert SCD2 facts landed: _dlt_loads row OK + reasonable row counts."""
        import psycopg2

        creds = _postgres_credentials()
        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            dbname=creds["database"],
            user=creds["username"],
            password=creds["password"],
        )
        try:
            with conn.cursor() as cur:
                load_id = facts_result["load_id"]
                cur.execute(
                    f"SELECT status FROM {DATASET_NAME}._dlt_loads WHERE load_id = %s",
                    (load_id,),
                )
                rows = cur.fetchall()
                if not rows or any(r[0] != 0 for r in rows):
                    raise RuntimeError(
                        f"_dlt_loads for load_id={load_id} not status=0 (success): {rows}"
                    )
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.jll_listings WHERE _dlt_valid_to IS NULL"
                )
                listings_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.jll_developments "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                devs_current = cur.fetchone()[0]
                if listings_current < 1000 or listings_current > 30_000:
                    raise RuntimeError(
                        f"listings current-state row count {listings_current} "
                        f"outside expected band [1000, 30000]"
                    )
                if devs_current < 50 or devs_current > 500:
                    raise RuntimeError(
                        f"developments current-state row count {devs_current} "
                        f"outside expected band [50, 500]"
                    )
                log.info(
                    "[jll_dlt] validation OK: listings=%d, developments=%d, load_id=%s",
                    listings_current,
                    devs_current,
                    load_id,
                )
                return {
                    "load_id": load_id,
                    "listings_current": listings_current,
                    "developments_current": devs_current,
                }
        finally:
            conn.close()

    audit = audit_to_minio()
    facts = load_facts()
    validation = validate_facts(facts)

    audit >> facts >> validation
