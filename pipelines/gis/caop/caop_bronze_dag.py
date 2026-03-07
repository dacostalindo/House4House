"""
CAOP Bronze Loading — S08

Loads CAOP GeoPackage from MinIO into PostGIS bronze tables.
Three layers: freguesias (3,049), municipios (278), distritos (18).

Trigger manually from Airflow UI — no schedule.
No config parameters needed — loads the latest version from MinIO.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer definitions — maps GPKG layer names to bronze table configs
# ---------------------------------------------------------------------------

LAYERS = [
    {
        "gpkg_layer": "cont_freguesias",
        "table": "bronze_geo.raw_caop_freguesias",
        "fields": [
            ("dtmnfr", "VARCHAR(6)"),
            ("freguesia", "TEXT"),
            ("municipio", "TEXT"),
            ("distrito_ilha", "TEXT"),
            ("nuts3_cod", "VARCHAR(10)"),
            ("nuts3", "TEXT"),
            ("nuts2", "TEXT"),
            ("nuts1", "TEXT"),
            ("area_ha", "DOUBLE PRECISION"),
            ("perimetro_km", "INTEGER"),
            ("designacao_simplificada", "TEXT"),
        ],
        "geom_type": "MULTIPOLYGON",
        "expected_min": 3000,
    },
    {
        "gpkg_layer": "cont_municipios",
        "table": "bronze_geo.raw_caop_municipios",
        "fields": [
            ("dtmn", "VARCHAR(4)"),
            ("municipio", "TEXT"),
            ("distrito_ilha", "TEXT"),
            ("nuts3_cod", "VARCHAR(10)"),
            ("nuts3", "TEXT"),
            ("nuts2", "TEXT"),
            ("nuts1", "TEXT"),
            ("area_ha", "DOUBLE PRECISION"),
            ("perimetro_km", "INTEGER"),
            ("n_freguesias", "INTEGER"),
        ],
        "geom_type": "MULTIPOLYGON",
        "expected_min": 270,
    },
    {
        "gpkg_layer": "cont_distritos",
        "table": "bronze_geo.raw_caop_distritos",
        "fields": [
            ("dt", "VARCHAR(2)"),
            ("distrito", "TEXT"),
            ("nuts1_cod", "VARCHAR(10)"),
            ("nuts1", "TEXT"),
            ("area_ha", "DOUBLE PRECISION"),
            ("perimetro_km", "INTEGER"),
            ("n_municipios", "INTEGER"),
            ("n_freguesias", "DOUBLE PRECISION"),
        ],
        "geom_type": "MULTIPOLYGON",
        "expected_min": 18,
    },
]


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
        dag_id="s08_caop_bronze_load",
        description="Load CAOP boundaries from MinIO into PostGIS bronze tables",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["caop", "bronze", "geography", "postgis"],
    )
    def caop_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Download the latest CAOP GPKG from MinIO to a temp directory."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            # Find the latest CAOP version in MinIO
            objects = list(client.list_objects("raw", prefix="caop/", recursive=True))
            gpkg_objects = [o for o in objects if o.object_name.endswith(".gpkg")]
            if not gpkg_objects:
                raise RuntimeError("No CAOP GPKG found in MinIO at raw/caop/")

            latest = sorted(gpkg_objects, key=lambda o: o.object_name)[-1]
            log.info("[caop] Latest GPKG in MinIO: %s (%.1f MB)", latest.object_name, latest.size / 1e6)

            tmp_dir = tempfile.mkdtemp(prefix="caop_bronze_")
            local_path = os.path.join(tmp_dir, "caop.gpkg")
            client.fget_object("raw", latest.object_name, local_path)

            file_size = os.path.getsize(local_path)
            log.info("[caop] Downloaded to %s (%.1f MB)", local_path, file_size / 1e6)

            return {"gpkg_path": local_path, "tmp_dir": tmp_dir, "minio_object": latest.object_name}

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

            for layer in LAYERS:
                schema_table = layer["table"]
                cols = ", ".join(f"{name} {dtype}" for name, dtype in layer["fields"])
                ddl = f"""
                    CREATE TABLE IF NOT EXISTS {schema_table} (
                        {cols},
                        geom GEOMETRY({layer['geom_type']}, 3763),
                        _load_timestamp TIMESTAMPTZ DEFAULT NOW()
                    )
                """
                cur.execute(ddl)
                log.info("[caop] Ensured table %s exists", schema_table)

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_layer(fetch_result: dict, layer_config: dict) -> dict:
            """Load a single GPKG layer into its bronze table."""
            import psycopg2
            import psycopg2.extras
            from pyogrio.raw import read as raw_read
            from airflow.models import Variable

            gpkg_path = fetch_result["gpkg_path"]
            gpkg_layer = layer_config["gpkg_layer"]
            schema_table = layer_config["table"]
            field_names = [name for name, _ in layer_config["fields"]]

            log.info("[caop] Reading layer %s from %s", gpkg_layer, gpkg_path)
            result = raw_read(gpkg_path, layer=gpkg_layer)
            # raw_read returns (meta, fids, geometry, field_data)
            geometry = result[2]   # WKB bytes array
            field_data = result[3]

            n_features = len(geometry)
            log.info("[caop] Read %d features from %s", n_features, gpkg_layer)

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

            # Prepare rows
            rows = []
            for i in range(n_features):
                field_values = []
                for j in range(len(field_names)):
                    val = field_data[j][i]
                    # Convert numpy types to Python natives
                    if hasattr(val, "item"):
                        val = val.item()
                    field_values.append(val)
                wkb = bytes(geometry[i])
                field_values.append(wkb)
                rows.append(tuple(field_values))

            psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=500)
            conn.commit()

            cur.close()
            conn.close()

            log.info("[caop] Loaded %d rows into %s", n_features, schema_table)
            return {"table": schema_table, "rows_loaded": n_features}

        @task()
        def validate_counts(load_results: list[dict]) -> dict:
            """Verify row counts match expectations."""
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

            results = {}
            for layer in LAYERS:
                cur.execute(f"SELECT COUNT(*) FROM {layer['table']}")
                count = cur.fetchone()[0]
                expected_min = layer["expected_min"]
                if count < expected_min:
                    raise ValueError(
                        f"{layer['table']}: got {count} rows, expected >= {expected_min}"
                    )
                log.info("[caop] %s: %d rows (>= %d OK)", layer["table"], count, expected_min)
                results[layer["table"]] = count

            cur.close()
            conn.close()
            return results

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory after all loads complete."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[caop] Cleaned up %s", tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        tables_ready = create_tables(fetched)

        load_results = []
        for layer_cfg in LAYERS:
            result = load_layer(tables_ready, layer_cfg)
            load_results.append(result)

        validated = validate_counts(load_results)
        cleanup_temp(fetched, validated)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_scoped_build",
            conf={"select": "stg_caop_distritos+ stg_caop_municipios+ stg_caop_freguesias+"},
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return caop_bronze_load()


dag = _create_dag()
