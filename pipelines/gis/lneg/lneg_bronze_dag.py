# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/lneg.md for the canonical source spec.

"""
LNEG Bronze Loading — GeoJSON → PostGIS

Loads the per-layer GeoJSONs written by `lneg_ingestion` from MinIO into
generic-properties bronze tables under `bronze_geology` / `bronze_hydrology`.
Properties are stored as JSONB so dbt staging models can pick the columns
they need without us pre-committing to a schema per layer (geology folhas
have inconsistent schemas, hidrogeo has its own).

Schema per bronze table (uniform across all LNEG layers):
    feature_id      INTEGER     -- from properties.OBJECTID when available
    layer_name      VARCHAR(64) -- 'lneg_geology_folha1_nw' etc, denormalized
    properties      JSONB       -- all ArcGIS REST feature properties
    geom            GEOMETRY(GEOMETRY, 3763) -- ALREADY in EPSG:3763
    _source_url     TEXT        -- MinIO object name
    _load_timestamp TIMESTAMPTZ -- when this row was inserted

A GIST index on `geom` and a GIN index on `properties` are auto-created per
table (matches srup_ogc_bronze_dag convention).

KEY DIFFERENCE FROM SRUP OGC LOADER: ArcGIS REST was queried with `outSR=3763`
(see ArcgisRestAdapter.fetch_to), so the GeoJSON coords are ALREADY in PT-TM06.
We SetSRID directly (no ST_Transform needed). This matches the APA pre-flight
verification which confirmed PT-TM06 coords arrived.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.lneg.lneg_config import (
    LNEG_CONFIG,
    LNEG_LAYERS,
    MINIO_BUCKET,
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


INSERT_TEMPLATE = """
INSERT INTO {table} (feature_id, layer_name, properties, geom, _source_url)
VALUES (
    %s, %s, %s,
    ST_SetSRID(ST_GeomFromGeoJSON(%s), 3763),
    %s
)
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = LNEG_CONFIG

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
        tags=["lneg", "arcgis_rest", "bronze", "postgis"],
    )
    def lneg_bronze_load():
        @task()
        def fetch_files_from_minio() -> dict:
            """Download the latest GeoJSON for each layer from MinIO."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            tmp_dir = tempfile.mkdtemp(prefix="lneg_bronze_")
            files: list[dict] = []

            for layer in LNEG_LAYERS:
                prefix = f"{minio_prefix_for(layer)}/"
                objects = list(client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True))
                geojson_objects = [o for o in objects if o.object_name.endswith(".geojson")]
                if not geojson_objects:
                    log.warning(
                        "[lneg] No GeoJSON found for %s at %s%s — skipping",
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
                    "[lneg] downloaded %s (%.1f MB) for %s",
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
                raise RuntimeError("No LNEG GeoJSON files in MinIO. Run lneg_ingestion first.")

            return {"tmp_dir": tmp_dir, "files": files}

        @task()
        def create_tables(fetch_result: dict) -> list[dict]:
            """Create per-layer bronze tables + indexes (idempotent).

            Returns the per-layer file list directly for downstream `.expand()`.
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
                log.info("[lneg] ensured table %s", table)
            cur.close()
            conn.close()
            return fetch_result["files"]

        @task()
        def load_layer(file_info: dict) -> dict:
            """Stream features into the bronze table for one layer."""
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 100
            local_path = file_info["local_path"]
            table = file_info["bronze_table"]
            name = file_info["name"]
            source_url = file_info["minio_object"]

            log.info("[lneg] loading %s into %s", local_path, table)

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
                fid = props.get("OBJECTID")

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
            log.info("[lneg] loaded %d rows into %s", total, table)
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
                log.info("[lneg] %s: %d rows", r["name"], n)
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
                log.info("[lneg] cleaned %s", tmp_dir)

        fetched = fetch_files_from_minio()
        files = create_tables(fetched)
        loaded = load_layer.expand(file_info=files)
        validated = validate_counts(loaded)
        cleanup_temp(fetched, validated)

    return lneg_bronze_load()


dag = _create_dag()
