"""imovirtual PT — dlt-driven SCD2 bronze ingestion DAG.

Direct Next.js `_next/data` JSON ingest (no scraping vendor). Design locked in
wiki/decisions/2026-06-05-imovirtual-portal-onboarding.md.

Tasks (in order):

  audit_to_minio   — best-effort: dump Pass-1 list page 1 (devs national +
                     terreno Aveiro) to s3://raw/imovirtual/... as an audit copy.
                     dlt fetches independently; an audit failure does NOT block.

  load_facts       — runs imovirtual_developments_facts_source: developments +
                     development_units SCD2 tables + two heartbeat sidecars.
                     NATIONAL scope. Hard-fails the DAG on error.

  load_plots       — runs imovirtual_plots_facts_source: plots SCD2 + heartbeat.
                     AVEIRO scope. Separate dlt pipeline (own pipelines_dir).

  validate_facts   — asserts both loads landed (_dlt_loads.status=0) and
                     current-state row counts are within scope-sized bands.

Schedule: 0 6 * * 4 (Thursdays 06:00 UTC) — staggered off idealista (Wed).

No `load_refs`: imovirtual carries no lookup tables (the Nexus payload is
self-describing via `localizedValue`), so the zome refs task is omitted.

Backfill note: dlt SCD2 boundary_timestamp is NOT wired (day 0 = today), same
as the other portals.
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

from pipelines.portals.imovirtual.source import (
    DEV_SCOPE,
    PLOT_SCOPE,
    _iter_search,
    imovirtual_developments_facts_source,
    imovirtual_plots_facts_source,
)

log = logging.getLogger(__name__)

PIPELINES_DIR = "/opt/airflow/dlt_state/imovirtual_developments"
PIPELINES_DIR_PLOTS = "/opt/airflow/dlt_state/imovirtual_plots"
DATASET_NAME = "bronze_listings"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "imovirtual"

# Current-state row-count bands (per scope; widen after the first national run).
DEV_BAND = (500, 1500)  # ~810 national developments
UNIT_BAND = (2000, 30_000)  # ~11 listed units/dev × ~810 devs
PLOT_BAND = (1000, 8000)  # ~4.8k Aveiro terreno


def _postgres_credentials() -> dict:
    return {
        "host": os.environ["WAREHOUSE_HOST"],
        "port": int(os.environ.get("WAREHOUSE_PORT", "5432")),
        "username": os.environ["WAREHOUSE_USER"],
        "password": os.environ["WAREHOUSE_PASSWORD"],
        "database": os.environ["WAREHOUSE_DB"],
    }


def _alert_on_failure(context: dict) -> None:
    ti = context.get("task_instance")
    log.error(
        "[ALERT] %s.%s failed (run %s): %s",
        ti.dag_id,
        ti.task_id,
        context.get("run_id"),
        context.get("exception"),
    )


default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": _alert_on_failure,
}


with DAG(
    dag_id="imovirtual_dlt",
    description=(
        "imovirtual PT bronze ingestion via dlt + Next.js _next/data JSON. "
        "Developments + units (national) and plots (Aveiro), SCD2 + heartbeat sidecars."
    ),
    schedule="0 6 * * 4",
    start_date=datetime(2026, 1, 1),  # static past date; manual triggers must satisfy this
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["imovirtual", "bronze", "dlt", "scd2", "next-data"],
) as dag:

    @task()
    def audit_to_minio() -> dict:
        """Best-effort raw-JSON dump of Pass-1 list page 1 (devs + plots) to MinIO."""
        from airflow.models import Variable
        from minio import Minio

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        client = Minio(
            Variable.get("MINIO_ENDPOINT", default_var="minio:9000"),
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

        # First search page only ("site shape didn't change" snapshot) per grain.
        dev_page1 = []
        for i, card in enumerate(_iter_search("empreendimento", DEV_SCOPE)):
            dev_page1.append(card)
            if i >= 35:  # one page (36 items)
                break
        _put("empreendimento/page1", dev_page1)

        plot_page1 = []
        for i, card in enumerate(_iter_search("terreno", PLOT_SCOPE)):
            plot_page1.append(card)
            if i >= 35:
                break
        _put("terreno/page1", plot_page1)

        log.info("[imovirtual_dlt] audit upload complete: %d files", len(uploaded))
        return {"uploaded": uploaded, "ts": ts}

    @task()
    def load_facts() -> dict:
        """Developments + units SCD2 + heartbeats (national). Hard fail on error."""
        pipeline = dlt.pipeline(
            pipeline_name="imovirtual_developments_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR,
        )
        info = pipeline.run(imovirtual_developments_facts_source())
        log.info("[imovirtual_dlt] facts load: %s", info)
        return {"load_id": pipeline.last_trace.last_load_info.loads_ids[-1]}

    @task()
    def load_plots() -> dict:
        """Plots SCD2 + heartbeat (Aveiro). Separate dlt pipeline."""
        pipeline = dlt.pipeline(
            pipeline_name="imovirtual_plots_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR_PLOTS,
        )
        info = pipeline.run(imovirtual_plots_facts_source())
        log.info("[imovirtual_dlt] plots load: %s", info)
        loads = pipeline.last_trace.last_load_info.loads_ids
        return {"load_id": loads[-1] if loads else None}

    @task()
    def validate_facts(facts_result: dict, plots_result: dict) -> dict:
        """Assert both loads landed + current-state counts within scope bands."""
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

                def _current(table: str) -> int:
                    cur.execute(
                        f"SELECT count(*) FROM {DATASET_NAME}.{table} WHERE _dlt_valid_to IS NULL"
                    )
                    return cur.fetchone()[0]

                def _check_load(load_id: str | None, what: str) -> None:
                    if load_id is None:
                        raise RuntimeError(f"{what} load_id is None — load did not run")
                    cur.execute(
                        f"SELECT status FROM {DATASET_NAME}._dlt_loads WHERE load_id = %s",
                        (load_id,),
                    )
                    rows = cur.fetchall()
                    if not rows or any(r[0] != 0 for r in rows):  # 0 = success
                        raise RuntimeError(f"{what} _dlt_loads not status=0: {rows}")

                _check_load(facts_result.get("load_id"), "facts")
                _check_load(plots_result.get("load_id"), "plots")

                devs = _current("imovirtual_developments")
                units = _current("imovirtual_development_units")
                plots_n = _current("imovirtual_plots")

                for n, band, label in (
                    (devs, DEV_BAND, "developments"),
                    (units, UNIT_BAND, "development_units"),
                    (plots_n, PLOT_BAND, "plots"),
                ):
                    if n < band[0] or n > band[1]:
                        raise RuntimeError(f"{label} current-state count {n} outside band {band}")

                log.info(
                    "[imovirtual_dlt] validation OK: developments=%d, units=%d, plots=%d",
                    devs,
                    units,
                    plots_n,
                )
                return {
                    "developments_current": devs,
                    "units_current": units,
                    "plots_current": plots_n,
                }
        finally:
            conn.close()

    audit = audit_to_minio()
    facts = load_facts()
    plots_load = load_plots()
    validation = validate_facts(facts, plots_load)

    # Sequential, NOT parallel: each load is a single ~30-120 min synchronous
    # crawl; running both at once starves the task heartbeat on a loaded box and
    # trips the scheduler's zombie detector. Serializing halves peak CPU/network.
    audit >> facts >> plots_load >> validation
