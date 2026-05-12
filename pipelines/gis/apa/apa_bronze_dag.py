# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/apa.md for the canonical source spec.

"""
APA ARPSI Bronze Loading — GeoJSON → PostGIS

Loads the ARPSI GeoJSON written by `apa_arpsi_ingestion` from MinIO into
`bronze_hydrology.raw_apa_arpsi_floodplain`. Typed schema with one row per
flood polygon, key column `return_period_years` (T100 vs T1000) drives the
`flood_class` derivation in dbt staging.

Geometry arrives in EPSG:3763 (server-side reproject via outSR=3763), so we
SetSRID directly — no ST_Transform.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.apa.apa_config import (
    APA_CONFIG,
    BRONZE_SCHEMA_TABLE,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA_TABLE} (
    feature_id            INTEGER,        -- OBJECTID
    river_basin           TEXT,           -- RHidro (e.g. PTRH4A Vouga)
    location              TEXT,           -- Local
    designation           TEXT,           -- Designa (free-form site name)
    source                TEXT,           -- Fonte (data source)
    publication_date      TIMESTAMPTZ,    -- Data
    return_period_years   INTEGER,        -- TRetorno (100 or 1000)
    geocode               INTEGER,        -- GEOCOD (region/district code)
    geom                  GEOMETRY(GEOMETRY, 3763),
    _source_url           TEXT,
    _load_timestamp       TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_raw_apa_arpsi_geom
    ON {BRONZE_SCHEMA_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_raw_apa_arpsi_return_period
    ON {BRONZE_SCHEMA_TABLE} (return_period_years);
"""


INSERT_SQL = f"""
INSERT INTO {BRONZE_SCHEMA_TABLE} (
    feature_id, river_basin, location, designation,
    source, publication_date, return_period_years, geocode,
    geom, _source_url
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s, %s,
    ST_SetSRID(ST_GeomFromGeoJSON(%s), 3763),
    %s
)
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = APA_CONFIG

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
        tags=["apa", "arcgis_rest", "bronze", "postgis"],
    )
    def apa_arpsi_bronze_load():
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
                raise RuntimeError(f"No APA ARPSI GeoJSON in MinIO at {MINIO_PREFIX}/")

            latest = sorted(geojsons, key=lambda o: o.object_name)[-1]
            tmp_dir = tempfile.mkdtemp(prefix="apa_arpsi_bronze_")
            local_path = os.path.join(tmp_dir, "apa_arpsi.geojson")
            client.fget_object(MINIO_BUCKET, latest.object_name, local_path)
            size = os.path.getsize(local_path)
            log.info(
                "[apa_arpsi] downloaded %s (%.1f MB)",
                latest.object_name,
                size / 1000000.0,
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
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_INDEXES_SQL)
            log.info("[apa_arpsi] ensured table %s exists", BRONZE_SCHEMA_TABLE)
            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_features(fetch_result: dict) -> dict:
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 50
            local_path = fetch_result["local_path"]
            source_url = fetch_result["minio_object"]

            log.info("[apa_arpsi] loading %s (streaming)", local_path)

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

            # Stream-friendly newline-separated FeatureCollection parser.
            # ARPSI is small (188 features) but the streaming pattern is reusable.
            with open(local_path, encoding="utf-8") as f:
                full = f.read()
            data = json.loads(full)
            for feat in data.get("features", []):
                if feat.get("type") != "Feature":
                    continue
                props = feat.get("properties", {})
                geom = feat.get("geometry")
                if not geom:
                    continue

                fid = props.get("OBJECTID")
                tret = props.get("TRetorno")
                gcod = props.get("GEOCOD")
                date_raw = props.get("Data")
                pub_date = None
                if date_raw is not None:
                    try:
                        if isinstance(date_raw, (int, float)):
                            # ArcGIS REST sometimes returns epoch ms
                            _dt = datetime.utcfromtimestamp(date_raw / 1000)
                            pub_date = _dt
                        else:
                            pub_date = str(date_raw)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pub_date = None

                batch.append(
                    (
                        fid,
                        props.get("RHidro", ""),
                        props.get("Local", ""),
                        props.get("Designa", ""),
                        props.get("Fonte", ""),
                        pub_date,
                        tret,
                        gcod,
                        json.dumps(geom),
                        source_url,
                    )
                )

                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                    total += len(batch)
                    batch.clear()

            if batch:
                psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                total += len(batch)

            conn.commit()
            cur.close()
            conn.close()

            log.info("[apa_arpsi] loaded %d rows into %s", total, BRONZE_SCHEMA_TABLE)
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
            log.info("[apa_arpsi] %s: %d rows", BRONZE_SCHEMA_TABLE, n)
            if n == 0:
                raise ValueError(f"No rows in {BRONZE_SCHEMA_TABLE} after loading")
            return {"table": BRONZE_SCHEMA_TABLE, "count": n}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info("[apa_arpsi] cleaned %s", tmp_dir)

        fetched = fetch_from_minio()
        ready = create_table(fetched)
        loaded = load_features(ready)
        validated = validate_count(loaded)
        cleanup_temp(fetched, validated)

    return apa_arpsi_bronze_load()


dag = _create_dag()
