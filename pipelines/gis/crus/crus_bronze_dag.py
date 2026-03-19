"""
CRUS Bronze Loading — GeoJSON → PostGIS

Loads CRUS GeoJSON files from MinIO into bronze_regulatory.raw_crus_ordenamento.
One table for all municipalities — per-municipality full-refresh (DELETE + INSERT).

Trigger manually or via TriggerDagRunOperator from crus_ingestion.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.crus.crus_config import (
    BRONZE_SCHEMA_TABLE,
    MUNICIPALITIES,
    MINIO_BUCKET,
    MINIO_PREFIX,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bronze table DDL
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BRONZE_SCHEMA_TABLE} (
    feature_id          INTEGER,
    municipality_code   VARCHAR(4),
    municipality_name   VARCHAR(100),
    classe              VARCHAR(50),
    categoria           VARCHAR(200),
    designacao          TEXT,
    area_ha             DOUBLE PRECISION,
    escala              VARCHAR(10),
    data_publicacao_pdm TIMESTAMPTZ,
    fonte               VARCHAR(30),
    autor               VARCHAR(10),
    geom                GEOMETRY(GEOMETRY, 3763),
    _source_url         TEXT,
    _load_timestamp     TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_crus_ord_geom
    ON {BRONZE_SCHEMA_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_crus_ord_muni
    ON {BRONZE_SCHEMA_TABLE} (municipality_code);
"""

INSERT_SQL = f"""
INSERT INTO {BRONZE_SCHEMA_TABLE} (
    feature_id, municipality_code, municipality_name,
    classe, categoria, designacao, area_ha, escala,
    data_publicacao_pdm, fonte, autor,
    geom, _source_url
) VALUES (
    %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s,
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
        dag_id="crus_bronze_load",
        description="Load CRUS GeoJSON from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["crus", "bronze", "postgis", "zoning"],
    )
    def crus_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Find the latest CRUS GeoJSON files in MinIO for each municipality."""
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

            tmp_dir = tempfile.mkdtemp(prefix="crus_bronze_")
            files: list[dict] = []

            for muni in MUNICIPALITIES:
                prefix = f"{MINIO_PREFIX}/{muni.name_lower}/"
                objects = list(
                    client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
                )
                geojson_objects = [
                    o for o in objects if o.object_name.endswith(".geojson")
                ]

                if not geojson_objects:
                    log.warning(
                        "[crus] No GeoJSON found for %s at %s%s",
                        muni.name,
                        MINIO_BUCKET,
                        prefix,
                    )
                    continue

                latest = sorted(geojson_objects, key=lambda o: o.object_name)[-1]
                local_path = os.path.join(tmp_dir, f"{muni.name_lower}_crus.geojson")
                client.fget_object(MINIO_BUCKET, latest.object_name, local_path)

                file_size = os.path.getsize(local_path)
                log.info(
                    "[crus] Downloaded %s (%.1f MB) for %s",
                    latest.object_name,
                    file_size / 1e6,
                    muni.name,
                )

                files.append(
                    {
                        "code": muni.code,
                        "name": muni.name,
                        "local_path": local_path,
                        "minio_object": latest.object_name,
                    }
                )

            if not files:
                raise RuntimeError(
                    "No CRUS GeoJSON files found in MinIO for any municipality"
                )

            return {"tmp_dir": tmp_dir, "files": files}

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
            log.info("[crus] Ensured table %s exists", BRONZE_SCHEMA_TABLE)

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_municipalities(fetch_result: dict) -> list[dict]:
            """Load all municipalities' CRUS GeoJSON into the bronze table."""
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
                    code = file_info["code"]
                    name = file_info["name"]
                    local_path = file_info["local_path"]
                    source_url = file_info["minio_object"]

                    log.info("[crus] Loading %s (%s) from %s", name, code, local_path)

                    with open(local_path, "r", encoding="utf-8") as f:
                        fc = json.load(f)

                    features = fc.get("features", [])
                    log.info("[crus] Parsed %d features for %s", len(features), name)

                    # Per-municipality full refresh
                    cur.execute(
                        f"DELETE FROM {BRONZE_SCHEMA_TABLE} WHERE municipality_code = %s",
                        (code,),
                    )
                    deleted = cur.rowcount
                    if deleted:
                        log.info("[crus] Deleted %d existing rows for %s", deleted, name)

                    rows = []
                    for feat in features:
                        props = feat.get("properties", {})
                        geom = feat.get("geometry")
                        if geom is None:
                            continue

                        rows.append(
                            (
                                props.get("ID"),
                                props.get("DTCC", code),
                                props.get("Municipio", name),
                                props.get("Classe"),
                                props.get("Categoria"),
                                props.get("Designacao_PlantaOrdenamento"),
                                props.get("Area_Ha"),
                                props.get("Escala_PlantaOrdenamento"),
                                props.get("Data_PublicacaoPDM"),
                                props.get("Fonte"),
                                props.get("Autor"),
                                json.dumps(geom),
                                source_url,
                            )
                        )

                    psycopg2.extras.execute_batch(cur, INSERT_SQL, rows, page_size=500)
                    conn.commit()

                    log.info("[crus] Loaded %d rows into %s for %s", len(rows), BRONZE_SCHEMA_TABLE, name)
                    results.append({"code": code, "name": name, "rows_loaded": len(rows)})

                cur.close()
            finally:
                conn.close()
            return results

        @task()
        def validate_counts(load_results: list[dict]) -> dict:
            """Verify row counts per municipality are reasonable.

            load_results is accepted as a parameter to establish the Airflow
            dependency chain (ensures validation runs after loading).
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
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT municipality_code, COUNT(*) FROM {BRONZE_SCHEMA_TABLE} "
                    f"GROUP BY municipality_code ORDER BY municipality_code"
                )
                counts = dict(cur.fetchall())
                cur.close()
            finally:
                conn.close()

            total = sum(counts.values())
            log.info("[crus] Total rows in %s: %d", BRONZE_SCHEMA_TABLE, total)
            for code, count in counts.items():
                log.info("[crus]   %s: %d rows", code, count)

            if total == 0:
                raise ValueError(f"No rows in {BRONZE_SCHEMA_TABLE} after loading")

            return {"counts": counts, "total": total}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[crus] Cleaned up %s", tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        tables_ready = create_table(fetched)

        load_results = load_municipalities(tables_ready)

        validated = validate_counts(load_results)
        cleanup_temp(fetched, validated)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_crus_build",
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return crus_bronze_load()


dag = _create_dag()
