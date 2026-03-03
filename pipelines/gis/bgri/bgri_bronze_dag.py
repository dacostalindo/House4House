"""
BGRI Bronze Loading — S12

Loads BGRI Census 2021 GeoPackage from MinIO into PostGIS bronze table.
Single layer: BGRI21_CONT (203,264 statistical subsections).

Trigger manually from Airflow UI — no schedule (Census 2021 is static).
No config parameters needed — loads the latest version from MinIO.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import timedelta

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer definition — maps GPKG layer to bronze table config
# ---------------------------------------------------------------------------

LAYER = {
    "gpkg_layer": "BGRI21_CONT",
    "table": "bronze_ine.raw_bgri",
    "fields": [
        ("objectid", "INTEGER"),
        ("bgri2021", "VARCHAR(20)"),
        ("dt21", "VARCHAR(2)"),
        ("dtmn21", "VARCHAR(4)"),
        ("dtmnfr21", "VARCHAR(6)"),
        ("dtmnfrsec21", "VARCHAR(10)"),
        ("secnum21", "VARCHAR(4)"),
        ("ssnum21", "VARCHAR(4)"),
        ("secssnum21", "VARCHAR(8)"),
        ("subseccao", "VARCHAR(20)"),
        ("nuts1", "VARCHAR(50)"),
        ("nuts2", "VARCHAR(50)"),
        ("nuts3", "VARCHAR(50)"),
        # Buildings (12)
        ("n_edificios_classicos", "DOUBLE PRECISION"),
        ("n_edificios_class_const_1_ou_2_aloj", "DOUBLE PRECISION"),
        ("n_edificios_class_const_3_ou_mais_alojamentos", "DOUBLE PRECISION"),
        ("n_edificios_exclusiv_resid", "DOUBLE PRECISION"),
        ("n_edificios_1_ou_2_pisos", "DOUBLE PRECISION"),
        ("n_edificios_3_ou_mais_pisos", "DOUBLE PRECISION"),
        ("n_edificios_constr_antes_1945", "DOUBLE PRECISION"),
        ("n_edificios_constr_1946_1980", "DOUBLE PRECISION"),
        ("n_edificios_constr_1981_2000", "DOUBLE PRECISION"),
        ("n_edificios_constr_2001_2010", "DOUBLE PRECISION"),
        ("n_edificios_constr_2011_2021", "DOUBLE PRECISION"),
        ("n_edificios_com_necessidades_reparacao", "DOUBLE PRECISION"),
        # Dwellings (8)
        ("n_alojamentos_total", "DOUBLE PRECISION"),
        ("n_alojamentos_familiares", "DOUBLE PRECISION"),
        ("n_alojamentos_fam_class_rhabitual", "DOUBLE PRECISION"),
        ("n_alojamentos_fam_class_vagos_ou_resid_secundaria", "DOUBLE PRECISION"),
        ("n_rhabitual_acessivel_cadeiras_rodas", "DOUBLE PRECISION"),
        ("n_rhabitual_com_estacionamento", "DOUBLE PRECISION"),
        ("n_rhabitual_prop_ocup", "DOUBLE PRECISION"),
        ("n_rhabitual_arrendados", "DOUBLE PRECISION"),
        # Households (5)
        ("n_agregados_domesticos_privados", "DOUBLE PRECISION"),
        ("n_adp_1_ou_2_pessoas", "DOUBLE PRECISION"),
        ("n_adp_3_ou_mais_pessoas", "DOUBLE PRECISION"),
        ("n_nucleos_familiares", "DOUBLE PRECISION"),
        ("n_nucleos_familiares_com_filhos_tendo_o_mais_novo_menos_de_25", "DOUBLE PRECISION"),
        # Population (7)
        ("n_individuos", "DOUBLE PRECISION"),
        ("n_individuos_h", "DOUBLE PRECISION"),
        ("n_individuos_m", "DOUBLE PRECISION"),
        ("n_individuos_0_14", "DOUBLE PRECISION"),
        ("n_individuos_15_24", "DOUBLE PRECISION"),
        ("n_individuos_25_64", "DOUBLE PRECISION"),
        ("n_individuos_65_ou_mais", "DOUBLE PRECISION"),
        # Shape metrics
        ("shape_length", "DOUBLE PRECISION"),
        ("shape_area", "DOUBLE PRECISION"),
    ],
    "geom_type": "MULTIPOLYGON",
    "expected_min": 200_000,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="s12_bgri_bronze_load",
        description="Load BGRI Census 2021 from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["bgri", "census", "bronze", "ine", "postgis"],
    )
    def bgri_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Download the BGRI GPKG from MinIO to a temp directory."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            objects = list(client.list_objects("raw", prefix="bgri/", recursive=True))
            gpkg_objects = [o for o in objects if o.object_name.endswith(".gpkg")]
            if not gpkg_objects:
                raise RuntimeError("No BGRI GPKG found in MinIO at raw/bgri/")

            latest = sorted(gpkg_objects, key=lambda o: o.object_name)[-1]
            log.info("[bgri] Latest GPKG in MinIO: %s (%.1f MB)", latest.object_name, latest.size / 1e6)

            tmp_dir = tempfile.mkdtemp(prefix="bgri_bronze_")
            local_path = os.path.join(tmp_dir, "bgri.gpkg")
            client.fget_object("raw", latest.object_name, local_path)

            file_size = os.path.getsize(local_path)
            log.info("[bgri] Downloaded to %s (%.1f MB)", local_path, file_size / 1e6)

            return {"gpkg_path": local_path, "tmp_dir": tmp_dir, "minio_object": latest.object_name}

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

            cols = ", ".join(f"{name} {dtype}" for name, dtype in LAYER["fields"])
            ddl = f"""
                CREATE TABLE IF NOT EXISTS {LAYER['table']} (
                    {cols},
                    geom GEOMETRY({LAYER['geom_type']}, 3763),
                    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
                )
            """
            cur.execute(ddl)
            log.info("[bgri] Ensured table %s exists", LAYER["table"])

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_bgri(fetch_result: dict) -> dict:
            """Load BGRI GPKG layer into bronze table."""
            import psycopg2
            import psycopg2.extras
            from pyogrio.raw import read as raw_read
            from airflow.models import Variable

            gpkg_path = fetch_result["gpkg_path"]
            gpkg_layer = LAYER["gpkg_layer"]
            schema_table = LAYER["table"]
            field_names = [name for name, _ in LAYER["fields"]]

            log.info("[bgri] Reading layer %s from %s", gpkg_layer, gpkg_path)
            result = raw_read(gpkg_path, layer=gpkg_layer)
            # raw_read returns (meta, fids, geometry, field_data)
            geometry = result[2]
            field_data = result[3]

            n_features = len(geometry)
            log.info("[bgri] Read %d features from %s", n_features, gpkg_layer)

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            # Truncate for idempotent full-refresh
            cur.execute(f"TRUNCATE {schema_table}")

            # Build INSERT statement
            placeholders = ", ".join(["%s"] * len(field_names))
            insert_sql = (
                f"INSERT INTO {schema_table} ({', '.join(field_names)}, geom) "
                f"VALUES ({placeholders}, ST_GeomFromWKB(%s, 3763))"
            )

            # Prepare and insert in batches to manage memory
            batch_size = 5000
            total_inserted = 0
            for start in range(0, n_features, batch_size):
                end = min(start + batch_size, n_features)
                rows = []
                for i in range(start, end):
                    field_values = []
                    for j in range(len(field_names)):
                        val = field_data[j][i]
                        if hasattr(val, "item"):
                            val = val.item()
                        field_values.append(val)
                    wkb = bytes(geometry[i])
                    field_values.append(wkb)
                    rows.append(tuple(field_values))

                psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
                total_inserted += len(rows)
                log.info("[bgri] Inserted %d / %d rows", total_inserted, n_features)

            conn.commit()
            cur.close()
            conn.close()

            log.info("[bgri] Loaded %d rows into %s", n_features, schema_table)
            return {"table": schema_table, "rows_loaded": n_features}

        @task()
        def validate_counts(load_result: dict) -> dict:
            """Verify row count matches expectations."""
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

            cur.execute(f"SELECT COUNT(*) FROM {LAYER['table']}")
            count = cur.fetchone()[0]
            expected_min = LAYER["expected_min"]
            if count < expected_min:
                raise ValueError(
                    f"{LAYER['table']}: got {count} rows, expected >= {expected_min}"
                )
            log.info("[bgri] %s: %d rows (>= %d OK)", LAYER["table"], count, expected_min)

            cur.close()
            conn.close()
            return {"table": LAYER["table"], "count": count}

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory after load completes."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[bgri] Cleaned up %s", tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        table_ready = create_table(fetched)
        loaded = load_bgri(table_ready)
        validated = validate_counts(loaded)
        cleanup_temp(fetched, validated)

    return bgri_bronze_load()


dag = _create_dag()
