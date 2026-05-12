# v2 scope — preserved from .pyc decompile. Day-8 evaluation gate per Sprint-08 plan.
# See wiki/sources/srup-ogc.md for the canonical source spec.

"""
SRUP OGC Bronze Loading — GeoJSON → PostGIS

Loads GeoJSON files written by `srup_ogc_ingestion` from MinIO into per-layer
bronze tables under `bronze_regulatory.raw_*`. Properties are stored as JSONB
so dbt staging models can pick the columns they need without us pre-committing
to a schema per layer.

Schema per bronze table (uniform across all SRUP OGC layers):
    feature_id      INTEGER     -- from properties.fid / properties.id when available
    layer_name      VARCHAR(64) -- 'srup_ren_areal' etc, denormalized for ad-hoc queries
    properties      JSONB       -- all OGC API feature properties
    geom            GEOMETRY(GEOMETRY, 3763) -- native EPSG:3763 (no reprojection)
    _source_url     TEXT        -- MinIO object name
    _load_timestamp TIMESTAMPTZ -- when this row was inserted

A GIST index on `geom` and a GIN index on `properties` are auto-created per
table (matches the existing `srup_bronze_dag.py` convention).

Trigger manually or via TriggerDagRunOperator from `srup_ogc_ingestion`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.srup_ogc.srup_ogc_config import (
    MINIO_BUCKET,
    SRUP_OGC_CONFIG,
    SRUP_OGC_LAYERS,
    minio_prefix_for,
)

log = logging.getLogger(__name__)


def _create_table_sql(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        feature_id      INTEGER,
        layer_name      VARCHAR(64),
        properties      JSONB,
        geom            GEOMETRY(GEOMETRY, 3763),
        _source_url     TEXT,
        _load_timestamp TIMESTAMPTZ DEFAULT NOW()
    );
    """


def _create_indexes_sql(table: str) -> str:
    short = table.split(".")[-1]
    return f"""
    CREATE INDEX IF NOT EXISTS idx_{short}_geom
        ON {table} USING GIST(geom);
    CREATE INDEX IF NOT EXISTS idx_{short}_props
        ON {table} USING GIN(properties);
    """


# OGC API serves geometries in EPSG:4326 — transform to PT-TM06 (EPSG:3763) on insert.
INSERT_TEMPLATE = """
INSERT INTO {table} (feature_id, layer_name, properties, geom, _source_url)
VALUES (
    %s, %s, %s,
    ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3763),
    %s
)
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = SRUP_OGC_CONFIG

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id=cfg.bronze_dag_id,
        description=cfg.description_bronze,
        schedule=None,
        start_date=cfg.start_date,
        catchup=False,
        default_args=default_args,
        max_active_tasks=cfg.max_active_tasks,
        tags=["srup", "ogc_api", "bronze", "postgis"],
    )
    def srup_ogc_bronze_load():
        @task()
        def fetch_files_from_minio() -> dict:
            """Download the latest GeoJSON for each WS2a layer from MinIO."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            tmp_dir = tempfile.mkdtemp(prefix="srup_ogc_bronze_")
            files: list[dict] = []

            for layer in SRUP_OGC_LAYERS:
                prefix = f"{minio_prefix_for(layer)}/"
                objects = list(client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True))
                geojson_objects = [o for o in objects if o.object_name.endswith(".geojson")]
                if not geojson_objects:
                    log.warning(
                        "[srup_ogc] No GeoJSON found for layer %s at %s%s — skipping",
                        layer.name,
                        MINIO_BUCKET,
                        prefix,
                    )
                    continue

                latest = sorted(geojson_objects, key=lambda o: o.object_name)[-1]
                local_path = os.path.join(tmp_dir, f"{layer.name}.geojson")
                client.fget_object(MINIO_BUCKET, latest.object_name, local_path)
                size = os.path.getsize(local_path)
                log.info(
                    "[srup_ogc] downloaded %s (%.1f MB) for %s",
                    latest.object_name,
                    size / 1000000.0,
                    layer.name,
                )

                files.append(
                    {
                        "name": layer.name,
                        "bronze_table": layer.bronze_table,
                        "local_path": local_path,
                        "minio_object": latest.object_name,
                    }
                )

            if not files:
                raise RuntimeError(
                    "No SRUP OGC GeoJSON files found in MinIO for any layer. "
                    "Run srup_ogc_ingestion first."
                )

            return {"tmp_dir": tmp_dir, "files": files}

        @task()
        def create_tables(fetch_result: dict) -> list[dict]:
            """Create per-layer bronze tables + indexes (idempotent).

            Returns the per-layer file list directly so downstream `.expand()`
            can iterate without subscripting an XCom (Airflow doesn't support
            `xcom_arg["key"]` in expand inputs).
            """
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
            for f in fetch_result["files"]:
                table = f["bronze_table"]
                cur.execute(_create_table_sql(table))
                cur.execute(_create_indexes_sql(table))
                log.info("[srup_ogc] ensured table %s", table)
            cur.close()
            conn.close()
            return fetch_result["files"]

        @task()
        def load_layer(file_info: dict) -> dict:
            """Stream features into the bronze table for one layer."""
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 50
            local_path = file_info["local_path"]
            table = file_info["bronze_table"]
            name = file_info["name"]
            source_url = file_info["minio_object"]

            log.info("[srup_ogc] loading %s into %s", local_path, table)

            with open(local_path, encoding="utf-8") as f:
                data = json.load(f)

            insert_sql = INSERT_TEMPLATE.format(table=table)

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute(f"TRUNCATE {table}")
            conn.commit()

            batch: list[tuple] = []
            total = 0

            for feat in data.get("features", []):
                if feat.get("type") != "Feature":
                    continue
                props = feat.get("properties", {}) or {}
                geom = feat.get("geometry")
                if not geom:
                    continue
                fid = props.get("fid") or props.get("id")

                batch.append(
                    (
                        fid,
                        name,
                        json.dumps(props),
                        json.dumps(geom),
                        source_url,
                    )
                )

                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_batch(cur, insert_sql, batch, page_size=BATCH_SIZE)
                    total += len(batch)
                    batch.clear()

            if batch:
                psycopg2.extras.execute_batch(cur, insert_sql, batch, page_size=BATCH_SIZE)
                total += len(batch)

            conn.commit()
            cur.close()
            conn.close()
            log.info("[srup_ogc] loaded %d rows into %s", total, table)
            return {"name": name, "table": table, "rows_loaded": total}

        @task()
        def validate_counts(load_results: list[dict]) -> dict:
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            summary: list[dict] = []
            for r in load_results:
                cur.execute(f"SELECT COUNT(*) FROM {r['table']}")
                n = cur.fetchone()[0]
                log.info("[srup_ogc] %s: %d rows", r["name"], n)
                if n == 0:
                    raise ValueError(f"No rows in {r['table']} after load")
                summary.append({**r, "rows": n})
            cur.close()
            conn.close()
            return {"summary": summary}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info("[srup_ogc] cleaned %s", tmp_dir)

        fetched = fetch_files_from_minio()
        files_list = create_tables(fetched)
        load_results = load_layer.expand(file_info=files_list)
        validated = validate_counts(load_results)
        cleanup_temp(fetched, validated)

        if cfg.trigger_dbt_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_dbt = TriggerDagRunOperator(
                task_id="trigger_dbt_srup_build",
                trigger_dag_id=cfg.trigger_dbt_dag_id,
                wait_for_completion=False,
            )
            validated >> trigger_dbt

    return srup_ogc_bronze_load()


dag = _create_dag()
