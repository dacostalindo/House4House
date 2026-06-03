# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/crus-ogc.md for the canonical source spec.

"""
CRUS National OGC Bronze Loading — GeoJSON → PostGIS

Loads the CRUS national GeoJSON written by `crus_ogc_ingestion` from MinIO
into `bronze_regulatory.raw_crus_national_ogc`. Unlike the SRUP omnibus
loader (which uses generic JSONB properties), CRUS gets a typed schema
mirroring the legacy `raw_crus_ordenamento` columns + a `municipality_code`
derived from the OGC `dtcc` field.

Lessons baked in from WS2a:
  - CRS fix: `ST_Transform(ST_SetSRID(geom, 4326), 3763)` since the OGC API
    serves all collections in EPSG:4326, not the native PT-TM06.
  - BATCH_SIZE = 20 to stay under the Linux OOM-killer threshold for huge
    geometry batches.
  - GIST + btree indexes auto-created (matches the WS2a + cadastro convention).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

import ijson

from pipelines.gis.crus_ogc.crus_ogc_config import (
    BRONZE_SCHEMA_TABLE,
    CRUS_OGC_CONFIG,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA_TABLE} (
    feature_id            INTEGER,
    municipality_code     VARCHAR(4),    -- derived: LPAD(dtcc, 4, '0')
    municipality_name     TEXT,          -- from properties.municipio
    classe                TEXT,          -- from properties.classe_2021
    categoria             TEXT,          -- from properties.categoria_2021
    designacao            TEXT,          -- from properties.classificacao_e_qualificacao
    area_ha               DOUBLE PRECISION,
    escala                TEXT,          -- from properties.escala_origem
    data_publicacao_pdm   TIMESTAMPTZ,   -- from properties.data_pub_origem
    fonte                 TEXT,
    autor                 TEXT,
    situacao_pdm          TEXT,
    registo_ou_deposito   TEXT,
    geom                  GEOMETRY(GEOMETRY, 3763),
    _source_url           TEXT,
    _load_timestamp       TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_raw_crus_national_ogc_geom
    ON {BRONZE_SCHEMA_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_raw_crus_national_ogc_muni
    ON {BRONZE_SCHEMA_TABLE} (municipality_code);
CREATE INDEX IF NOT EXISTS idx_raw_crus_national_ogc_classe
    ON {BRONZE_SCHEMA_TABLE} (classe);
"""


INSERT_SQL = f"""
INSERT INTO {BRONZE_SCHEMA_TABLE} (
    feature_id, municipality_code, municipality_name,
    classe, categoria, designacao,
    area_ha, escala, data_publicacao_pdm,
    fonte, autor, situacao_pdm, registo_ou_deposito,
    geom, _source_url
) VALUES (
    %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s,
    ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3763),
    %s
)
"""


def _create_dag():
    from airflow.decorators import dag, task

    cfg = CRUS_OGC_CONFIG

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
        tags=["crus", "ogc_api", "bronze", "postgis"],
    )
    def crus_ogc_bronze_load():
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
                raise RuntimeError(f"No CRUS OGC GeoJSON in MinIO at {MINIO_PREFIX}/")

            latest = sorted(geojsons, key=lambda o: o.object_name)[-1]
            tmp_dir = tempfile.mkdtemp(prefix="crus_ogc_bronze_")
            local_path = os.path.join(tmp_dir, "crus_national.geojson")
            client.fget_object(MINIO_BUCKET, latest.object_name, local_path)
            size = os.path.getsize(local_path)
            log.info(
                "[crus_ogc] downloaded %s (%.1f MB)",
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
            log.info("[crus_ogc] ensured table %s exists", BRONZE_SCHEMA_TABLE)
            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_features(fetch_result: dict) -> dict:
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            BATCH_SIZE = 20
            local_path = fetch_result["local_path"]
            source_url = fetch_result["minio_object"]

            log.info("[crus_ogc] loading %s (streaming)", local_path)

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

            # ijson.items() streams the GeoJSON FeatureCollection one feature at
            # a time, keeping RAM flat regardless of input size. Previous
            # `json.load(f)` OOM'd the Airflow worker on national CRUS (~2.1 GB,
            # 236k features). Sprint-09 WS4 PR B. `features.item` is the
            # canonical jsonpath for FeatureCollection elements; binary mode
            # (rb) for ijson's performance path.
            # use_float=True: avoid Decimal returns that break json.dumps(geom).
            with open(local_path, "rb") as f:
                for feat in ijson.items(f, "features.item", use_float=True):
                    if feat.get("type") != "Feature":
                        continue
                    props = feat.get("properties", {})
                    geom = feat.get("geometry")
                    if not geom:
                        continue

                    dtcc_raw = props.get("dtcc", "")
                    try:
                        muni_code = str(dtcc_raw).zfill(4) if dtcc_raw else None
                    except (TypeError, ValueError):
                        muni_code = None
                    fid = props.get("fid")
                    try:
                        area = (
                            float(props.get("area_ha"))
                            if props.get("area_ha") is not None
                            else None
                        )
                    except (TypeError, ValueError):
                        area = None

                    batch.append(
                        (
                            fid,
                            muni_code,
                            props.get("municipio", ""),
                            props.get("classe_2021", ""),
                            props.get("categoria_2021", ""),
                            props.get("classificacao_e_qualificacao", ""),
                            area,
                            props.get("escala_origem", ""),
                            props.get("data_pub_origem"),
                            props.get("fonte", ""),
                            props.get("autor", ""),
                            props.get("situacao_pdm", ""),
                            props.get("registo_ou_deposito", ""),
                            json.dumps(geom),
                            source_url,
                        )
                    )

                    if len(batch) >= BATCH_SIZE:
                        psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                        total += len(batch)
                        if total % 5000 == 0:
                            log.info("[crus_ogc] inserted %d rows", total)
                        batch.clear()

            if batch:
                psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
                total += len(batch)

            conn.commit()
            cur.close()
            conn.close()

            log.info("[crus_ogc] loaded %d rows into %s", total, BRONZE_SCHEMA_TABLE)
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
            log.info("[crus_ogc] %s: %d rows", BRONZE_SCHEMA_TABLE, n)
            if n == 0:
                raise ValueError(f"No rows in {BRONZE_SCHEMA_TABLE} after loading")
            return {"table": BRONZE_SCHEMA_TABLE, "count": n}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info("[crus_ogc] cleaned %s", tmp_dir)

        fetched = fetch_from_minio()
        ready = create_table(fetched)
        loaded = load_features(ready)
        validated = validate_count(loaded)
        cleanup_temp(fetched, validated)

        if cfg.trigger_dbt_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_dbt = TriggerDagRunOperator(
                task_id="trigger_dbt_srup_build",
                trigger_dag_id=cfg.trigger_dbt_dag_id,
                wait_for_completion=False,
            )
            validated >> trigger_dbt

    return crus_ogc_bronze_load()


dag = _create_dag()
