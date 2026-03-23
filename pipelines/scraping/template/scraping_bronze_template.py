"""
Bronze Loading Template — Flow B

Factory that creates Airflow DAGs for loading scraped JSONL from MinIO
into PostGIS bronze tables.

Extracted from the common 5-task pattern across INE, BPStat, ECB,
Eurostat, and Idealista bronze DAGs.

Pipeline scope: list MinIO files → create table → load records → validate → trigger dbt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class BronzeTableConfig:
    """
    All parameters needed to instantiate a bronze loading DAG.

    --- Data transformation ---
    flatten_fn receives the raw data (dict for JSON, list[dict] for JSONL)
    and returns a list of tuples matching the INSERT statement's %s placeholders.

    --- Idempotency ---
    delete_before_insert: If True, deletes existing rows before inserting.
    delete_sql: SQL DELETE statement with a single %s placeholder.
    delete_key_fn: Extracts the delete key value from a MinIO object name.
    """

    # --- DAG identity ---
    dag_id: str
    source_name: str
    description: str

    # --- Database ---
    schema_name: str            # e.g. "bronze_regulatory"
    table_name: str             # e.g. "raw_sce_pce"
    create_table_sql: str       # Full CREATE TABLE IF NOT EXISTS DDL
    create_indexes_sql: list[str] = field(default_factory=list)
    insert_sql: str = ""        # INSERT statement with %s placeholders

    # --- MinIO ---
    minio_bucket: str = "raw"
    minio_prefix: str = ""      # e.g. "sce_pce" — scans raw/sce_pce/

    # --- Data transformation ---
    flatten_fn: Optional[Callable] = None  # (raw_data, batch_id, minio_path) -> list[tuple]
    file_format: str = "jsonl"  # "json" or "jsonl"

    # --- Idempotency ---
    delete_before_insert: bool = True
    delete_sql: str = ""        # e.g. "DELETE FROM ... WHERE _scrape_date = %s"
    delete_key_fn: Optional[Callable] = None  # (object_name) -> key value

    # --- Batch processing ---
    insert_batch_size: int = 10_000
    insert_page_size: int = 1_000

    # --- Orchestration ---
    trigger_dag_id: Optional[str] = None

    # --- DAG settings ---
    tags: list[str] = field(default_factory=list)
    retries: int = 1
    retry_delay_minutes: int = 5


# ---------------------------------------------------------------------------
# DAG factory
# ---------------------------------------------------------------------------


def create_bronze_loading_dag(config: BronzeTableConfig):
    """
    Returns an Airflow DAG for loading scraped data into a bronze table.

    Task graph:

        list_minio_files
                │
        create_table
                │
        load_records
                │
        validate_counts
                │
        trigger_dbt_pipeline (optional)
    """
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": config.retries,
        "retry_delay": timedelta(minutes=config.retry_delay_minutes),
    }

    @dag(
        dag_id=config.dag_id,
        description=config.description,
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["bronze", "postgis"] + config.tags,
    )
    def bronze_loading_dag():

        @task()
        def list_minio_files() -> dict:
            """Find JSONL/JSON files in MinIO for this source."""
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            prefix = config.minio_prefix
            ext = ".jsonl" if config.file_format == "jsonl" else ".json"

            objects = list(client.list_objects(
                config.minio_bucket, prefix=f"{prefix}/", recursive=True,
            ))
            data_files = [
                o.object_name for o in objects
                if o.object_name.endswith(ext)
            ]

            log.info("[%s] Found %d %s files in s3://%s/%s/",
                     config.source_name, len(data_files), ext,
                     config.minio_bucket, prefix)

            # Group by region (second path component after prefix)
            by_region: dict[str, list[str]] = {}
            for f in data_files:
                # Path: {prefix}/{region}/{date}/{timestamp}.jsonl
                relative = f[len(prefix):].strip("/")
                parts = relative.split("/")
                region = parts[0] if parts else "unknown"
                by_region.setdefault(region, []).append(f)

            # Take latest file per region
            latest: dict[str, str] = {}
            for region, files in by_region.items():
                latest[region] = sorted(files)[-1]
                log.info("[%s] %s → %s", config.source_name, region, latest[region])

            return latest

        @task()
        def create_table() -> None:
            """Create the bronze table if it doesn't exist."""
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            try:
                conn.autocommit = True
                cur = conn.cursor()

                cur.execute(config.create_table_sql)
                for idx_sql in config.create_indexes_sql:
                    cur.execute(idx_sql)

                log.info("[%s] Ensured %s.%s exists with indexes",
                         config.source_name, config.schema_name, config.table_name)

                cur.close()
            finally:
                conn.close()

        @task()
        def load_records(latest_files: dict) -> dict:
            """Parse files from MinIO and load into the bronze table."""
            import psycopg2
            import psycopg2.extras
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            try:
                cur = conn.cursor()

                batch_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                results: dict[str, int] = {}
                total_rows = 0

                for region, object_name in latest_files.items():
                    # Read from MinIO
                    resp = client.get_object(config.minio_bucket, object_name)
                    raw_content = resp.read().decode("utf-8")
                    resp.close()
                    resp.release_conn()

                    # Parse based on format
                    if config.file_format == "jsonl":
                        raw_records = [
                            json.loads(line)
                            for line in raw_content.strip().split("\n")
                            if line.strip()
                        ]
                    else:
                        raw_records = json.loads(raw_content)
                        if not isinstance(raw_records, list):
                            raw_records = [raw_records]

                    # Idempotency: delete existing rows
                    if config.delete_before_insert and config.delete_sql and config.delete_key_fn:
                        delete_key = config.delete_key_fn(object_name)
                        cur.execute(config.delete_sql, (delete_key,))
                        deleted = cur.rowcount
                        log.info("[%s] %s: deleted %d existing rows (key=%s)",
                                 config.source_name, region, deleted, delete_key)

                    # Flatten and insert
                    region_batch_id = f"{region}_{batch_id}"
                    rows = config.flatten_fn(raw_records, region_batch_id, object_name)

                    if not rows:
                        log.warning("[%s] %s: no records to load", config.source_name, region)
                        results[region] = 0
                        continue

                    # Batch insert
                    for start in range(0, len(rows), config.insert_batch_size):
                        batch = rows[start:start + config.insert_batch_size]
                        psycopg2.extras.execute_batch(
                            cur, config.insert_sql, batch,
                            page_size=config.insert_page_size,
                        )

                    conn.commit()
                    total_rows += len(rows)
                    results[region] = len(rows)
                    log.info("[%s] %s: loaded %d rows", config.source_name, region, len(rows))

                cur.close()

                log.info("[%s] Total: %d rows across %d regions",
                         config.source_name, total_rows, len(results))
                return results
            finally:
                conn.close()

        @task()
        def validate_counts(load_results: dict) -> dict:
            """Verify the table has data."""
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            try:
                cur = conn.cursor()

                fqn = f"{config.schema_name}.{config.table_name}"
                cur.execute(f"SELECT COUNT(*) FROM {fqn}")
                total = cur.fetchone()[0]

                cur.close()
            finally:
                conn.close()

            log.info("[%s] Total rows in %s: %d", config.source_name, fqn, total)
            return {"total_rows": total, "regions_loaded": len(load_results)}

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_records(files)
        table_ready >> loaded
        validated = validate_counts(loaded)

        if config.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_dbt = TriggerDagRunOperator(
                task_id="trigger_dbt_pipeline",
                trigger_dag_id=config.trigger_dag_id,
                wait_for_completion=True,
                reset_dag_run=True,
                poke_interval=10,
            )
            validated >> trigger_dbt

    return bronze_loading_dag()
