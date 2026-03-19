"""
SRUP Bronze Loading — GeoJSON → PostGIS

Loads SRUP GeoJSON files from MinIO into per-category bronze tables.
Properties stored as JSONB — field extraction happens in dbt staging models.

Trigger manually or via TriggerDagRunOperator from srup_ingestion.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.srup.srup_config import (
    ALL_CATEGORIES,
    BRONZE_TABLES,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bronze table DDL (shared schema for all SRUP categories)
# ---------------------------------------------------------------------------


def _create_table_sql(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        feature_id      INTEGER,
        category        VARCHAR(10),
        feature_type    TEXT,
        properties      JSONB,
        geom            GEOMETRY(GEOMETRY, 3763),
        _source_url     TEXT,
        _load_timestamp TIMESTAMPTZ DEFAULT NOW()
    );
    """


def _create_indexes_sql(table: str) -> str:
    short = table.split(".")[-1]  # e.g. "raw_srup_ic"
    return f"""
    CREATE INDEX IF NOT EXISTS idx_{short}_geom
        ON {table} USING GIST(geom);
    CREATE INDEX IF NOT EXISTS idx_{short}_props
        ON {table} USING GIN(properties);
    """


INSERT_TEMPLATE = """
INSERT INTO {table} (
    feature_id, category, feature_type, properties,
    geom, _source_url
) VALUES (
    %s, %s, %s, %s,
    ST_SetSRID(ST_GeomFromGeoJSON(%s), 3763),
    %s
)
"""


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="srup_bronze_load",
        description="Load SRUP GeoJSON from MinIO into PostGIS bronze tables",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["srup", "bronze", "postgis", "constraints"],
    )
    def srup_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Find the latest SRUP GeoJSON files in MinIO for each category."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=False,
            )

            tmp_dir = tempfile.mkdtemp(prefix="srup_bronze_")
            files: list[dict] = []

            for category in ALL_CATEGORIES:
                prefix = f"{MINIO_PREFIX}/{category}/"
                objects = list(
                    client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
                )
                geojson_objects = [
                    o for o in objects if o.object_name.endswith(".geojson")
                ]

                if not geojson_objects:
                    log.warning(
                        "[srup] No GeoJSON found for %s at %s%s",
                        category,
                        MINIO_BUCKET,
                        prefix,
                    )
                    continue

                latest = sorted(geojson_objects, key=lambda o: o.object_name)[-1]
                local_path = os.path.join(tmp_dir, f"{category}.geojson")
                client.fget_object(MINIO_BUCKET, latest.object_name, local_path)

                file_size = os.path.getsize(local_path)
                log.info(
                    "[srup] Downloaded %s (%.1f MB) for %s",
                    latest.object_name,
                    file_size / 1e6,
                    category,
                )

                files.append(
                    {
                        "category": category,
                        "local_path": local_path,
                        "minio_object": latest.object_name,
                    }
                )

            if not files:
                raise RuntimeError(
                    "No SRUP GeoJSON files found in MinIO for any category"
                )

            return {"tmp_dir": tmp_dir, "files": files}

        @task()
        def create_tables(fetch_result: dict) -> dict:
            """Create bronze tables if they don't exist."""
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            conn.autocommit = True
            cur = conn.cursor()

            for file_info in fetch_result["files"]:
                category = file_info["category"]
                table = BRONZE_TABLES[category]
                cur.execute(_create_table_sql(table))
                cur.execute(_create_indexes_sql(table))
                log.info("[srup] Ensured table %s exists", table)

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_categories(fetch_result: dict) -> list[dict]:
            """Load all categories' GeoJSON into their bronze tables."""
            import psycopg2
            import psycopg2.extras
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
                results = []

                for file_info in fetch_result["files"]:
                    category = file_info["category"]
                    local_path = file_info["local_path"]
                    source_url = file_info["minio_object"]
                    table = BRONZE_TABLES[category]

                    log.info("[srup] Loading %s from %s", category, local_path)

                    with open(local_path, "r", encoding="utf-8") as f:
                        fc = json.load(f)

                    features = fc.get("features", [])
                    log.info("[srup] Parsed %d features for %s", len(features), category)

                    # Full refresh per category
                    cur.execute(f"TRUNCATE {table}")
                    log.info("[srup] Truncated %s", table)

                    insert_sql = INSERT_TEMPLATE.format(table=table)
                    rows = []
                    for feat in features:
                        props = feat.get("properties", {})
                        geom = feat.get("geometry")
                        if geom is None:
                            continue

                        rows.append(
                            (
                                props.get("ID"),
                                category,
                                feat.get("id", ""),  # WFS feature type hint
                                json.dumps(props, ensure_ascii=False),
                                json.dumps(geom),
                                source_url,
                            )
                        )

                    psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
                    conn.commit()

                    log.info(
                        "[srup] Loaded %d rows into %s", len(rows), table
                    )
                    results.append(
                        {"category": category, "table": table, "rows_loaded": len(rows)}
                    )

                cur.close()
            finally:
                conn.close()
            return results

        @task()
        def validate_counts(load_results: list[dict]) -> dict:
            """Verify row counts per category are reasonable."""
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
                counts = {}
                for result in load_results:
                    table = result["table"]
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    counts[result["category"]] = count
                    log.info("[srup] %s: %d rows", table, count)
                cur.close()
            finally:
                conn.close()

            total = sum(counts.values())
            log.info("[srup] Total rows across all tables: %d", total)

            if total == 0:
                raise ValueError("No rows in any SRUP bronze table after loading")

            return {"counts": counts, "total": total}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[srup] Cleaned up %s", tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        tables_ready = create_tables(fetched)
        load_results = load_categories(tables_ready)
        validated = validate_counts(load_results)
        cleanup_temp(fetched, validated)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_srup_build",
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return srup_bronze_load()


dag = _create_dag()
