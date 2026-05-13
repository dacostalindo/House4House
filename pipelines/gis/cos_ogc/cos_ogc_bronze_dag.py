"""
COS 2023 OGC Bronze Loading — GeoJSON → PostGIS

Loads the COS OGC GeoJSON written by `cos_ogc_ingestion` from MinIO into
`bronze_geo.raw_cos_national_ogc`. The OGC API publishes geometries in
EPSG:4326 → transformed to PT-TM06 (EPSG:3763) on insert.

Schema:
  - feature_id      INTEGER       (from properties.objectid)
  - municipio       TEXT          (from properties.Municipio, OGC-only)
  - nutsii          TEXT          (from properties.NUTSII, OGC-only)
  - nutsiii         TEXT          (from properties.NUTSIII, OGC-only)
  - cos23_n4_c      TEXT          (from properties.COS23_n4_C — same as legacy)
  - cos23_n4_l      TEXT          (from properties.COS23_n4_L — same as legacy)
  - area_ha         DOUBLE PRECISION  (computed `ST_Area(geom) / 10000`)
  - geom            GEOMETRY(GEOMETRY, 3763)
  - _source_url     TEXT
  - _load_timestamp TIMESTAMPTZ
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.cos_ogc.cos_ogc_config import (
    BRONZE_SCHEMA_TABLE,
    COS_OGC_CONFIG,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA_TABLE} (
    feature_id        INTEGER,
    municipio         TEXT,
    nutsii            TEXT,
    nutsiii           TEXT,
    cos23_n4_c        TEXT,
    cos23_n4_l        TEXT,
    area_ha           DOUBLE PRECISION,
    geom              GEOMETRY(GEOMETRY, 3763),
    _source_url       TEXT,
    _load_timestamp   TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_raw_cos_national_ogc_geom
    ON {BRONZE_SCHEMA_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_raw_cos_national_ogc_muni
    ON {BRONZE_SCHEMA_TABLE} (municipio);
CREATE INDEX IF NOT EXISTS idx_raw_cos_national_ogc_code
    ON {BRONZE_SCHEMA_TABLE} (cos23_n4_c);
"""


INSERT_SQL = f"""
INSERT INTO {BRONZE_SCHEMA_TABLE} (
    feature_id, municipio, nutsii, nutsiii,
    cos23_n4_c, cos23_n4_l,
    area_ha, geom, _source_url
)
SELECT
    %s, %s, %s, %s,
    %s, %s,
    ST_Area(transformed_geom) / 10000.0,
    transformed_geom,
    %s
FROM (
    SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3763) AS transformed_geom
) AS g
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = COS_OGC_CONFIG

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
        tags=["cos", "ogc_api", "bronze", "postgis", "land-use"],
    )
    def cos_ogc_bronze_load():
        @task()
        def fetch_from_minio() -> dict:
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            objects = list(
                client.list_objects(MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True)
            )
            geojsons = [o for o in objects if o.object_name.endswith(".geojson")]
            if not geojsons:
                raise RuntimeError(f"No COS OGC GeoJSON in MinIO at {MINIO_PREFIX}/")

            latest = sorted(geojsons, key=lambda o: o.object_name)[-1]
            tmp_dir = tempfile.mkdtemp(prefix="cos_ogc_bronze_")
            local_path = os.path.join(tmp_dir, "cos_ogc.geojson")
            client.fget_object(MINIO_BUCKET, latest.object_name, local_path)
            size = os.path.getsize(local_path)
            log.info(
                "[cos_ogc] downloaded %s (%.1f MB)",
                latest.object_name,
                size / 1_000_000.0,
            )
            return {
                "tmp_dir": tmp_dir,
                "local_path": local_path,
                "minio_object": latest.object_name,
            }

        @task()
        def create_table(fetch_result: dict) -> dict:
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
            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze_geo")
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_INDEXES_SQL)
            log.info("[cos_ogc] ensured table %s exists", BRONZE_SCHEMA_TABLE)
            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_features(fetch_result: dict) -> dict:
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 100
            local_path = fetch_result["local_path"]
            source_url = fetch_result["minio_object"]

            log.info("[cos_ogc] loading %s", local_path)

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute(f"TRUNCATE {BRONZE_SCHEMA_TABLE}")
            conn.commit()

            batch: list[tuple] = []
            total = 0

            with open(local_path, encoding="utf-8") as f:
                data = json.load(f)

            for feat in data.get("features", []):
                if feat.get("type") != "Feature":
                    continue
                props = feat.get("properties", {})
                geom = feat.get("geometry")
                if not geom:
                    continue

                batch.append(
                    (
                        props.get("objectid"),
                        props.get("Municipio", ""),
                        props.get("NUTSII", ""),
                        props.get("NUTSIII", ""),
                        props.get("COS23_n4_C", ""),
                        props.get("COS23_n4_L", ""),
                        source_url,
                        json.dumps(geom),
                    )
                )

                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                    total += len(batch)
                    if total % 5000 == 0:
                        log.info("[cos_ogc] inserted %d rows", total)
                    batch.clear()

            if batch:
                psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                total += len(batch)

            conn.commit()
            cur.close()
            conn.close()

            log.info("[cos_ogc] loaded %d rows into %s", total, BRONZE_SCHEMA_TABLE)
            return {"table": BRONZE_SCHEMA_TABLE, "rows_loaded": total}

        @task()
        def validate_count(load_result: dict) -> dict:
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
            cur.execute(f"SELECT COUNT(*) FROM {BRONZE_SCHEMA_TABLE}")
            n = cur.fetchone()[0]
            cur.close()
            conn.close()
            log.info("[cos_ogc] %s: %d rows", BRONZE_SCHEMA_TABLE, n)
            if n == 0:
                raise ValueError(f"No rows in {BRONZE_SCHEMA_TABLE} after loading")
            return {"table": BRONZE_SCHEMA_TABLE, "count": n}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info("[cos_ogc] cleaned %s", tmp_dir)

        fetched = fetch_from_minio()
        ready = create_table(fetched)
        loaded = load_features(ready)
        validated = validate_count(loaded)
        cleanup_temp(fetched, validated)

    return cos_ogc_bronze_load()


dag = _create_dag()
