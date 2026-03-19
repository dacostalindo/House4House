"""
Cadastro Predial Bronze Loading — GeoJSON → PostGIS

Loads Cadastro Predial GeoJSON from MinIO into bronze_regulatory.raw_cadastro.
Single file, full-refresh (TRUNCATE + INSERT).

GeoJSON features are in WGS84 (EPSG:4326) per OGC API spec.
Geometries are transformed to PT-TM06 (EPSG:3763) on insert.

Follows the same pattern as pdm_bronze_dag.py (GeoJSON → PostGIS).
Trigger manually or via TriggerDagRunOperator from cadastro_ingestion.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.cadastro.cadastro_config import (
    BRONZE_SCHEMA_TABLE,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bronze table DDL
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA_TABLE} (
    inspireid                    TEXT,
    nationalcadastralreference   TEXT,
    areavalue                    DOUBLE PRECISION,
    administrativeunit           VARCHAR(6),
    label                        TEXT,
    validfrom                    TIMESTAMPTZ,
    validto                      TIMESTAMPTZ,
    beginlifespanversion         TIMESTAMPTZ,
    geom                         GEOMETRY(MULTIPOLYGON, 3763),
    _source_url                  TEXT,
    _load_timestamp              TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_cadastro_geom
    ON {BRONZE_SCHEMA_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_cadastro_ref
    ON {BRONZE_SCHEMA_TABLE} (nationalcadastralreference);
CREATE INDEX IF NOT EXISTS idx_cadastro_admin
    ON {BRONZE_SCHEMA_TABLE} (administrativeunit);
"""

INSERT_SQL = f"""
INSERT INTO {BRONZE_SCHEMA_TABLE} (
    inspireid, nationalcadastralreference, areavalue,
    administrativeunit, label,
    validfrom, validto, beginlifespanversion,
    geom, _source_url
) VALUES (
    %s, %s, %s,
    %s, %s,
    %s, %s, %s,
    ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3763),
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
        dag_id="cadastro_bronze_load",
        description="Load Cadastro Predial GeoJSON from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["cadastro", "bronze", "parcels", "postgis"],
    )
    def cadastro_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Find the latest Cadastro GeoJSON in MinIO."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            objects = list(
                client.list_objects(MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True)
            )
            geojson_objects = [
                o for o in objects if o.object_name.endswith(".geojson")
            ]

            if not geojson_objects:
                raise RuntimeError(
                    f"No Cadastro GeoJSON found in MinIO at {MINIO_BUCKET}/{MINIO_PREFIX}/"
                )

            latest = sorted(geojson_objects, key=lambda o: o.object_name)[-1]

            tmp_dir = tempfile.mkdtemp(prefix="cadastro_bronze_")
            local_path = os.path.join(tmp_dir, "cadastro.geojson")
            client.fget_object(MINIO_BUCKET, latest.object_name, local_path)

            file_size = os.path.getsize(local_path)
            log.info("[cadastro] Downloaded %s (%.1f MB)", latest.object_name, file_size / 1e6)

            return {
                "tmp_dir": tmp_dir,
                "local_path": local_path,
                "minio_object": latest.object_name,
            }

        @task()
        def create_table(fetch_result: dict) -> dict:
            """Create bronze table if it doesn't exist."""
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
            log.info("[cadastro] Ensured table %s exists", BRONZE_SCHEMA_TABLE)

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_features(fetch_result: dict) -> dict:
            """Load Cadastro GeoJSON features into the bronze table.

            Streams the GeoJSON file line-by-line to avoid OOM on large datasets.
            The ingestion DAG writes one feature per line with comma separators,
            so we can parse features individually.
            """
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            local_path = fetch_result["local_path"]
            source_url = fetch_result["minio_object"]

            log.info("[cadastro] Loading %s (streaming)", local_path)

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            cur.execute(f"TRUNCATE {BRONZE_SCHEMA_TABLE}")

            batch_size = 5000
            batch = []
            total = 0

            with open(local_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().rstrip(",")
                    if not line or line == "]}":
                        continue
                    if line.startswith('{"type":"FeatureCollection"'):
                        continue
                    try:
                        feat = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if feat.get("type") != "Feature":
                        continue

                    props = feat.get("properties", {})
                    geom = feat.get("geometry")
                    if geom is None:
                        continue

                    batch.append((
                        props.get("inspireid"),
                        props.get("nationalcadastralreference"),
                        props.get("areavalue"),
                        props.get("administrativeunit"),
                        props.get("label"),
                        props.get("validfrom"),
                        props.get("validto"),
                        props.get("beginlifespanversion"),
                        json.dumps(geom),
                        source_url,
                    ))

                    if len(batch) >= batch_size:
                        psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=500)
                        conn.commit()
                        total += len(batch)
                        log.info("[cadastro] Inserted %d rows (total: %d)", len(batch), total)
                        batch = []

            if batch:
                psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=500)
                conn.commit()
                total += len(batch)

            log.info("[cadastro] Loaded %d rows into %s", total, BRONZE_SCHEMA_TABLE)

            cur.close()
            conn.close()
            return {"table": BRONZE_SCHEMA_TABLE, "rows_loaded": total}

        @task()
        def validate_counts(load_result: dict) -> dict:
            """Verify row count is reasonable."""
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
            count = cur.fetchone()[0]

            if count == 0:
                raise ValueError(f"No rows in {BRONZE_SCHEMA_TABLE} after loading")

            log.info("[cadastro] %s: %d rows", BRONZE_SCHEMA_TABLE, count)

            cur.close()
            conn.close()
            return {"table": BRONZE_SCHEMA_TABLE, "count": count}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[cadastro] Cleaned up %s", tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        tables_ready = create_table(fetched)
        loaded = load_features(tables_ready)
        validated = validate_counts(loaded)
        cleanup_temp(fetched, validated)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_cadastro_build",
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return cadastro_bronze_load()


dag = _create_dag()
