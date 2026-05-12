"""
DGT LiDAR Bronze Loading — manifest → PostGIS

For each LIDAR_LAYERS entry, reads the latest manifest.json from MinIO
(written by lidar_aveiro_ingestion) and populates a manifest table under
bronze_terrain.raw_lidar_*_manifest. ONE ROW PER TILE.

This is a manifest table — NOT a raster ingest. The actual GeoTIFF tiles
remain in MinIO; the manifest records WHERE they are + their footprint
geometry so that WS3b's parcel_zonal_stats DAG can locate the right tiles
via spatial join (parcel ↔ tile bbox intersect).

Schema per bronze table:
  tile_id              VARCHAR(64)    -- e.g. 'MDT-2m-163417-04-2024'
  collection_id        VARCHAR(32)    -- 'MDT-2m' or 'MDS-2m'
  geom                 GEOMETRY(GEOMETRY, 3763)  -- tile footprint, EPSG:3763
  minio_object         TEXT           -- e.g. 'lidar/MDT-2m/20260505/tiles/MDT-2m-...tif'
  acquisition_date     TIMESTAMPTZ    -- from STAC properties.datetime
  version              INTEGER        -- from STAC properties.version
  file_size_bytes      BIGINT
  pixel_type           VARCHAR(16)    -- e.g. 'Float32'
  nodata_value         DOUBLE PRECISION
  _source_url          TEXT           -- MinIO object name of the manifest
  _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.lidar.lidar_config import (
    LIDAR_CONFIG,
    LIDAR_LAYERS,
    MINIO_BUCKET,
    minio_prefix_for,
)

log = logging.getLogger(__name__)


def _create_table_sql(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        tile_id          VARCHAR(64),
        collection_id    VARCHAR(32),
        geom             GEOMETRY(GEOMETRY, 3763),
        minio_object     TEXT,
        acquisition_date TIMESTAMPTZ,
        version          INTEGER,
        file_size_bytes  BIGINT,
        pixel_type       VARCHAR(16),
        nodata_value     DOUBLE PRECISION,
        _source_url      TEXT,
        _load_timestamp  TIMESTAMPTZ DEFAULT NOW()
    );
    """


def _create_indexes_sql(table: str) -> str:
    short = table.split(".")[-1]
    return f"""
    CREATE INDEX IF NOT EXISTS idx_{short}_geom
        ON {table} USING GIST(geom);
    CREATE INDEX IF NOT EXISTS idx_{short}_tile_id
        ON {table} (tile_id);
    """


INSERT_TEMPLATE = """
INSERT INTO {table} (
    tile_id, collection_id, geom, minio_object, acquisition_date,
    version, file_size_bytes, pixel_type, nodata_value, _source_url
) VALUES (
    %s, %s,
    ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3763),
    %s, %s, %s, %s, %s, %s, %s
)
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = LIDAR_CONFIG

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
        tags=["lidar", "dgt_stac", "bronze", "postgis", "manifest"],
    )
    def lidar_aveiro_bronze_load():
        @task()
        def fetch_manifests_from_minio() -> dict:
            """Download the latest manifest.json for each LiDAR collection."""
            from airflow.models import Variable
            from minio import Minio

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            tmp_dir = tempfile.mkdtemp(prefix="lidar_bronze_")
            files: list[dict] = []

            for layer in LIDAR_LAYERS:
                prefix = f"{minio_prefix_for(layer)}/"
                objects = list(client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True))
                manifest_objects = [o for o in objects if o.object_name.endswith("manifest.json")]
                if not manifest_objects:
                    log.warning(
                        "[lidar] No manifest.json found for %s at %s%s — skipping",
                        layer.name,
                        MINIO_BUCKET,
                        prefix,
                    )
                    continue

                latest = sorted(manifest_objects, key=lambda o: o.object_name)[-1]
                local_path = os.path.join(tmp_dir, f"{layer.name}_manifest.json")
                client.fget_object(MINIO_BUCKET, latest.object_name, local_path)
                size = os.path.getsize(local_path)
                log.info(
                    "[lidar] downloaded %s (%.1f KB) for %s",
                    latest.object_name,
                    size / 1024,
                    layer.name,
                )

                files.append(
                    {
                        "name": layer.name,
                        "bronze_table": layer.bronze_table,
                        "collection_id": layer.collection_id,
                        "manifest_local_path": local_path,
                        "manifest_minio_object": latest.object_name,
                        "tiles_minio_prefix": latest.object_name.rsplit("/manifest.json", 1)[0]
                        + "/tiles",
                    }
                )

            if not files:
                raise RuntimeError("No LiDAR manifests in MinIO. Run lidar_aveiro_ingestion first.")

            return {"tmp_dir": tmp_dir, "files": files}

        @task()
        def create_tables(fetch_result: dict) -> list[dict]:
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
                log.info("[lidar] ensured table %s", table)
            cur.close()
            conn.close()
            return fetch_result["files"]

        @task()
        def load_layer(file_info: dict) -> dict:
            """Stream manifest items into the bronze manifest table."""
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 100
            local_path = file_info["manifest_local_path"]
            table = file_info["bronze_table"]
            collection_id = file_info["collection_id"]
            tiles_prefix = file_info["tiles_minio_prefix"]
            source_url = file_info["manifest_minio_object"]

            log.info("[lidar] loading manifest %s into %s", local_path, table)

            with open(local_path, encoding="utf-8") as f:
                manifest = json.load(f)

            items = manifest.get("items", [])
            if not items:
                raise RuntimeError(f"[{collection_id}] manifest has no items")

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

            for it in items:
                tile_id = it["tile_id"]
                geometry = it["geometry"]
                tile_object = f"{tiles_prefix}/{tile_id}.tif"
                pixel_type = it.get("pixel_type", "")
                nodata_value = it.get("nodata_value")

                batch.append(
                    (
                        tile_id,
                        collection_id,
                        json.dumps(geometry),
                        tile_object,
                        it.get("datetime"),
                        it.get("version"),
                        it.get("file_size_bytes"),
                        pixel_type,
                        nodata_value,
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

            log.info("[lidar] loaded %d manifest rows into %s", total, table)
            return {"name": file_info["name"], "table": table, "rows_loaded": total}

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
                log.info("[lidar] %s: %d manifest rows", r["name"], n)
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
                log.info("[lidar] cleaned %s", tmp_dir)

        fetched = fetch_manifests_from_minio()
        files = create_tables(fetched)
        loaded = load_layer.expand(file_info=files)
        validated = validate_counts(loaded)
        cleanup_temp(fetched, validated)

    return lidar_aveiro_bronze_load()


dag = _create_dag()
