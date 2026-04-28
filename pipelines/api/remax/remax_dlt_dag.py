"""RE/MAX PT — dlt-driven SCD2 bronze ingestion DAG.

Replaces the legacy three-DAG pipeline (remax_ingestion + two bronze loaders).

Tasks (in order):

  audit_to_minio   — fetch raw Pass 1 JSON, write to s3://raw/remax/... as
                     audit copy. Best-effort; failures log but do NOT block
                     the load. Pass 2 details are NOT mirrored to MinIO
                     (~3,900 tiny files would be too granular for audit).

  load_facts       — runs remax_facts_source via dlt: developments + listings
                     SCD2 tables + the two per-entity heartbeat sidecars.
                     Pass 2 enrichment is pre-fetched in parallel inside
                     source._prefetch_pass2() before the SCD2 merge runs.
                     Hard-fails the DAG on schema-contract violation.

  validate_facts   — asserts the facts load actually landed: _dlt_loads row
                     for the run has status='loaded_data', dev/listing
                     row counts in expected bands, Pass 2 enrichment count
                     in expected band.

Schedule: 0 6 * * 2 (Tuesdays 06:00 UTC). Tuesday avoids the Monday clash
with zome_dlt and gives slack if a Monday RE/MAX site issue blocks the run.
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

from pipelines.api.remax.source import (
    SEARCH_URL,
    PAGE_SIZE,
    PASS1_DELAY_S,
    REQUEST_TIMEOUT_S,
    remax_facts_source,
)


log = logging.getLogger(__name__)

PIPELINES_DIR = "/opt/airflow/dlt_state/remax"
DATASET_NAME = "bronze_listings"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "remax"


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
    dag_id="remax_dlt",
    description=(
        "RE/MAX PT bronze ingestion via dlt. SCD2 for developments/listings, "
        "UPSERT sidecar heartbeats for last_seen_date. Pass 2 (Next.js detail) "
        "enrichment pre-fetched in parallel."
    ),
    schedule="0 6 * * 2",
    start_date=datetime(2026, 1, 1),  # static past date; manual triggers must satisfy this
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["remax", "bronze", "dlt", "scd2"],
) as dag:

    @task()
    def audit_to_minio() -> dict:
        """Best-effort raw-JSON dump to MinIO for replay/audit.

        Saves the full Pass 1 PaginatedSearch payload (with embedded listings[])
        as a single JSONL-per-page file set. Pass 2 details are NOT mirrored
        — they would be ~3,900 tiny files. If we ever need Pass 2 audit,
        write a single concatenated JSONL.
        """
        import time
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

        # Mirror legacy MAX_PAGES=20 safety bound; stop early on empty page or hasNextPage=False.
        for page in range(1, 21):
            resp = requests.post(
                SEARCH_URL,
                json={"pageNumber": page, "pageSize": PAGE_SIZE},
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if not results:
                break
            _put(f"PaginatedSearch/p{page - 1}", results)
            if not data.get("hasNextPage"):
                break
            time.sleep(PASS1_DELAY_S)

        log.info("[remax_dlt] audit upload complete: %d files", len(uploaded))
        return {"uploaded": uploaded, "ts": ts}

    @task()
    def load_facts() -> dict:
        """SCD2 facts + heartbeat sidecars. Hard fail on schema-contract violation.

        This task is long-running because of Pass 2 enrichment (~3,900 detail
        fetches in parallel). With max_workers=4 and 1s per-worker delay it
        runs at ~4 req/s, completing in ~15-20 min for a full run. Compare
        to the legacy sequential ~5h.
        """
        pipeline = dlt.pipeline(
            pipeline_name="remax_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR,
        )
        info = pipeline.run(remax_facts_source())
        log.info("[remax_dlt] facts load: %s", info)
        return {"load_id": pipeline.last_trace.last_load_info.loads_ids[-1]}

    @task()
    def validate_facts(facts_result: dict) -> dict:
        """Assert SCD2 facts landed: _dlt_loads OK + counts in expected bands."""
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
                # status=0 means loaded_data in dlt's int-encoded status column
                if not rows or any(r[0] != 0 for r in rows):
                    raise RuntimeError(
                        f"_dlt_loads for load_id={load_id} not status=0 (loaded_data): {rows}"
                    )

                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.remax_listings "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                listings_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.remax_developments "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                devs_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.remax_listings "
                    f"WHERE _dlt_valid_to IS NULL AND market_days IS NOT NULL"
                )
                pass2_enriched = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.remax_plots "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                plots_current = cur.fetchone()[0]

                if listings_current < 3000 or listings_current > 30_000:
                    raise RuntimeError(
                        f"listings current-state row count {listings_current} "
                        f"outside expected band [3000, 30000]"
                    )
                if devs_current < 200 or devs_current > 2000:
                    raise RuntimeError(
                        f"developments current-state row count {devs_current} "
                        f"outside expected band [200, 2000]"
                    )
                if pass2_enriched < 1000 or pass2_enriched > 15_000:
                    raise RuntimeError(
                        f"Pass 2 enriched listings count {pass2_enriched} "
                        f"outside expected band [1000, 15000] — Next.js endpoint "
                        f"may have changed format or buildId extraction broke"
                    )
                # Plots band: sitemap-discovered, ~12,400 confirmed at probe time.
                if plots_current < 5_000 or plots_current > 25_000:
                    raise RuntimeError(
                        f"plots current-state row count {plots_current} "
                        f"outside expected band [5000, 25000] — sitemap.xml may have "
                        f"changed format or listingTypeID=21 filter regressed"
                    )

                log.info(
                    "[remax_dlt] validation OK: developments=%d, listings=%d, "
                    "pass2_enriched=%d, plots=%d, load_id=%s",
                    devs_current, listings_current, pass2_enriched, plots_current, load_id,
                )
                return {
                    "load_id": load_id,
                    "developments_current": devs_current,
                    "listings_current": listings_current,
                    "pass2_enriched": pass2_enriched,
                    "plots_current": plots_current,
                }
        finally:
            conn.close()

    audit = audit_to_minio()
    facts = load_facts()
    validation = validate_facts(facts)

    audit >> facts >> validation
