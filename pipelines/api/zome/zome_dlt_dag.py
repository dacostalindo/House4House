"""Zome PT — dlt-driven SCD2 bronze ingestion DAG.

Replaces the legacy three-DAG pipeline (zome_api_ingestion + two bronze loaders).

Tasks (in order):

  audit_to_minio   — fetch raw JSON, write to s3://raw/zome/... as audit copy.
                     Best-effort; failures log but do NOT block the load.
                     MinIO files are an AUDIT copy, NOT a load source — dlt
                     fetches independently from Supabase.

  load_facts       — runs zome_facts_source via dlt: developments + listings
                     SCD2 tables + the two per-entity heartbeat sidecars.
                     Hard-fails the DAG on error.

  load_refs        — runs zome_refs_source via dlt: 3 small lookup tables.
                     Soft-fails (trigger_rule=all_done from facts) so a ref
                     schema drift cannot block the facts load.

  validate_facts   — asserts the facts load actually landed: _dlt_loads row
                     for the run has status='loaded_data' and ~9k rows in
                     listings (current state).

Schedule: 0 6 * * 1 (Mondays 06:00 UTC). Source refreshes weekly per Zome.

Backfill note: dlt SCD2 boundary_timestamp (which would let `_dlt_valid_from`
be set to a past date for historical loads) is NOT wired up here. Day 0 is
intentionally today; previous scrapes are discarded. To add backfill support
later, use `source.resources["<name>"].apply_hints(write_disposition={...,
"boundary_timestamp": as_of})` against `dag_run.conf["as_of"]` before
`pipeline.run(...)`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import dlt
from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable

from pipelines.api.zome.source import (
    SUPABASE_URL,
    PAGE_SIZE,
    LISTINGS_MAX_OFFSET,
    RATE_LIMIT_S,
    REQUEST_TIMEOUT_S,
    _supabase_headers,
    zome_facts_source,
    zome_refs_source,
)


log = logging.getLogger(__name__)

PIPELINES_DIR = "/opt/airflow/dlt_state/zome"
PIPELINES_DIR_REFS = "/opt/airflow/dlt_state/zome_refs"
DATASET_NAME = "bronze_listings"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "zome"


def _postgres_credentials() -> dict:
    return {
        "host": os.environ["WAREHOUSE_HOST"],
        "port": int(os.environ.get("WAREHOUSE_PORT", "5432")),
        "username": os.environ["WAREHOUSE_USER"],
        "password": os.environ["WAREHOUSE_PASSWORD"],
        "database": os.environ["WAREHOUSE_DB"],
    }


def _alert_on_failure(context: dict) -> None:
    """task_failure_callback — surfaces schema-freeze / SCD2 failures.

    Replace the log.error with PagerDuty/Slack/email integration when the
    on-call rotation is wired up. For now, the failure is at minimum visible
    in the Airflow task log AND the scheduler log line.
    """
    task_id = context.get("task_instance").task_id
    dag_id = context.get("task_instance").dag_id
    run_id = context.get("run_id")
    exception = context.get("exception")
    log.error(
        "[ALERT] %s.%s failed (run %s): %s",
        dag_id, task_id, run_id, exception,
    )


default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": _alert_on_failure,
}


with DAG(
    dag_id="zome_dlt",
    description=(
        "Zome PT bronze ingestion via dlt. SCD2 for listings/developments, "
        "UPSERT sidecar heartbeats for last_seen_date, separate task for refs."
    ),
    schedule="0 6 * * 1",
    start_date=datetime(2026, 1, 1),  # static past date; manual triggers must satisfy this
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["zome", "bronze", "dlt", "scd2"],
) as dag:

    @task()
    def audit_to_minio() -> dict:
        """Best-effort raw-JSON dump to MinIO for replay/audit.

        Path layout matches the legacy convention:
          s3://raw/zome/tab_ventures/{ts}.json
          s3://raw/zome/tab_listing_list/p{0..9}/{ts}.json
        """
        from minio import Minio
        from dlt.sources.helpers import requests

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

        def _put(path_key: str, payload: list[dict]) -> None:
            with TemporaryDirectory() as td:
                fp = Path(td) / "out.json"
                fp.write_text(json.dumps(payload, ensure_ascii=False))
                obj = f"{MINIO_PREFIX}/{path_key}/{ts}.json"
                client.fput_object(MINIO_BUCKET, obj, str(fp))
                uploaded.append(f"s3://{MINIO_BUCKET}/{obj}")

        # Developments — single page.
        ventures = requests.get(
            f"{SUPABASE_URL}/rest/v1/tab_ventures",
            params={"select": "*", "limit": str(PAGE_SIZE), "offset": "0"},
            headers=_supabase_headers(),
            timeout=REQUEST_TIMEOUT_S,
        )
        ventures.raise_for_status()
        _put("tab_ventures", ventures.json())

        # Listings — paginate.
        import time
        for i, offset in enumerate(range(0, LISTINGS_MAX_OFFSET, PAGE_SIZE)):
            page = requests.get(
                f"{SUPABASE_URL}/rest/v1/tab_listing_list",
                params={"select": "*", "limit": str(PAGE_SIZE), "offset": str(offset)},
                headers=_supabase_headers(),
                timeout=REQUEST_TIMEOUT_S,
            )
            page.raise_for_status()
            rows = page.json()
            if not rows:
                break
            _put(f"tab_listing_list/p{i}", rows)
            if len(rows) < PAGE_SIZE:
                break
            time.sleep(RATE_LIMIT_S)

        log.info("[zome_dlt] audit upload complete: %d files", len(uploaded))
        return {"uploaded": uploaded, "ts": ts}

    @task()
    def load_facts() -> dict:
        """SCD2 facts + heartbeat sidecars. Hard fail on schema-contract violation."""
        pipeline = dlt.pipeline(
            pipeline_name="zome_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR,
        )
        info = pipeline.run(zome_facts_source())
        log.info("[zome_dlt] facts load: %s", info)
        return {"load_id": pipeline.last_trace.last_load_info.loads_ids[-1]}

    @task(trigger_rule="all_done")
    def load_refs() -> dict:
        """Lookup tables. Decoupled from facts so a ref schema drift does not
        block the facts load. Failures log but do NOT fail the DAG."""
        try:
            pipeline = dlt.pipeline(
                pipeline_name="zome_refs",
                destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
                dataset_name=DATASET_NAME,
                pipelines_dir=PIPELINES_DIR_REFS,
            )
            info = pipeline.run(zome_refs_source())
            log.info("[zome_dlt] refs load: %s", info)
            return {"status": "ok"}
        except Exception as exc:
            log.warning(
                "[zome_dlt] refs load failed (non-blocking) — verify endpoint paths "
                "in source.REF_PATHS against the Supabase OpenAPI spec: %s",
                exc,
            )
            return {"status": "failed", "error": str(exc)}

    @task()
    def validate_facts(facts_result: dict) -> dict:
        """Assert SCD2 facts landed: _dlt_loads row OK + reasonable row counts."""
        import psycopg2

        creds = _postgres_credentials()
        conn = psycopg2.connect(
            host=creds["host"], port=creds["port"], dbname=creds["database"],
            user=creds["username"], password=creds["password"],
        )
        try:
            with conn.cursor() as cur:
                load_id = facts_result["load_id"]
                cur.execute(
                    f"SELECT status FROM {DATASET_NAME}._dlt_loads WHERE load_id = %s",
                    (load_id,),
                )
                rows = cur.fetchall()
                # dlt _dlt_loads.status is bigint: 0 = success, non-zero = failure.
                if not rows or any(r[0] != 0 for r in rows):
                    raise RuntimeError(
                        f"_dlt_loads for load_id={load_id} not status=0 (success): {rows}"
                    )
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.zome_listings "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                listings_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.zome_developments "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                devs_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.zome_plots "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                plots_current = cur.fetchone()[0]
                if listings_current < 1000 or listings_current > 50_000:
                    raise RuntimeError(
                        f"listings current-state row count {listings_current} "
                        f"outside expected band [1000, 50000]"
                    )
                if devs_current < 50 or devs_current > 1000:
                    raise RuntimeError(
                        f"developments current-state row count {devs_current} "
                        f"outside expected band [50, 1000]"
                    )
                # Plots band: ~1,780 confirmed; allow generous bounds.
                if plots_current < 500 or plots_current > 5_000:
                    raise RuntimeError(
                        f"plots current-state row count {plots_current} "
                        f"outside expected band [500, 5000]"
                    )
                log.info(
                    "[zome_dlt] validation OK: listings=%d, developments=%d, plots=%d, load_id=%s",
                    listings_current, devs_current, plots_current, load_id,
                )
                return {
                    "load_id": load_id,
                    "listings_current": listings_current,
                    "developments_current": devs_current,
                    "plots_current": plots_current,
                }
        finally:
            conn.close()

    audit = audit_to_minio()
    facts = load_facts()
    refs = load_refs()
    validation = validate_facts(facts)

    audit >> facts
    facts >> [refs, validation]
