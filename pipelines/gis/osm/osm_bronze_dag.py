"""
OSM Bronze Loading — S09/S10/S11

Loads OpenStreetMap GeoPackage from MinIO into PostGIS bronze tables.
18 layers, ~4.5M features total. CRS is EPSG:4326 (WGS 84).

Trigger manually from Airflow UI — no schedule.
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
# Layer definitions — maps GPKG layer names to bronze table configs
# ---------------------------------------------------------------------------

# Base fields shared by most layers
_BASE = [
    ("osm_id", "TEXT"),
    ("code", "INTEGER"),
    ("fclass", "TEXT"),
    ("name", "TEXT"),
]

LAYERS = [
    # --- S09: POIs ---
    {
        "gpkg_layer": "gis_osm_pois_free",
        "table": "bronze_location.raw_osm_pois",
        "fields": list(_BASE),
        "geom_type": "POINT",
        "expected_min": 150_000,
    },
    {
        "gpkg_layer": "gis_osm_pois_a_free",
        "table": "bronze_location.raw_osm_pois_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 100_000,
    },
    {
        "gpkg_layer": "gis_osm_pofw_free",
        "table": "bronze_location.raw_osm_pofw",
        "fields": list(_BASE),
        "geom_type": "POINT",
        "expected_min": 1_000,
    },
    {
        "gpkg_layer": "gis_osm_pofw_a_free",
        "table": "bronze_location.raw_osm_pofw_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 5_000,
    },
    # --- S10: Transport ---
    {
        "gpkg_layer": "gis_osm_transport_free",
        "table": "bronze_location.raw_osm_transport",
        "fields": list(_BASE),
        "geom_type": "POINT",
        "expected_min": 40_000,
    },
    {
        "gpkg_layer": "gis_osm_transport_a_free",
        "table": "bronze_location.raw_osm_transport_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 500,
    },
    {
        "gpkg_layer": "gis_osm_railways_free",
        "table": "bronze_location.raw_osm_railways",
        "fields": _BASE + [
            ("layer", "INTEGER"),
            ("bridge", "TEXT"),
            ("tunnel", "TEXT"),
        ],
        "geom_type": "LINESTRING",
        "expected_min": 8_000,
    },
    # --- S11: Roads & Traffic ---
    {
        "gpkg_layer": "gis_osm_roads_free",
        "table": "bronze_location.raw_osm_roads",
        "fields": _BASE + [
            ("ref", "TEXT"),
            ("oneway", "TEXT"),
            ("maxspeed", "INTEGER"),
            ("layer", "INTEGER"),
            ("bridge", "TEXT"),
            ("tunnel", "TEXT"),
        ],
        "geom_type": "LINESTRING",
        "expected_min": 1_000_000,
    },
    {
        "gpkg_layer": "gis_osm_traffic_free",
        "table": "bronze_location.raw_osm_traffic",
        "fields": list(_BASE),
        "geom_type": "POINT",
        "expected_min": 100_000,
    },
    {
        "gpkg_layer": "gis_osm_traffic_a_free",
        "table": "bronze_location.raw_osm_traffic_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 40_000,
    },
    # --- Context layers ---
    {
        "gpkg_layer": "gis_osm_buildings_a_free",
        "table": "bronze_location.raw_osm_buildings_a",
        "fields": _BASE + [("type", "TEXT")],
        "geom_type": "MULTIPOLYGON",
        "expected_min": 1_500_000,
    },
    {
        "gpkg_layer": "gis_osm_landuse_a_free",
        "table": "bronze_location.raw_osm_landuse_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 300_000,
    },
    {
        "gpkg_layer": "gis_osm_natural_free",
        "table": "bronze_location.raw_osm_natural",
        "fields": list(_BASE),
        "geom_type": "POINT",
        "expected_min": 100_000,
    },
    {
        "gpkg_layer": "gis_osm_natural_a_free",
        "table": "bronze_location.raw_osm_natural_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 1_000,
    },
    {
        "gpkg_layer": "gis_osm_places_free",
        "table": "bronze_location.raw_osm_places",
        "fields": [
            ("osm_id", "TEXT"),
            ("code", "INTEGER"),
            ("fclass", "TEXT"),
            ("population", "INTEGER"),
            ("name", "TEXT"),
        ],
        "geom_type": "POINT",
        "expected_min": 20_000,
    },
    {
        "gpkg_layer": "gis_osm_places_a_free",
        "table": "bronze_location.raw_osm_places_a",
        "fields": [
            ("osm_id", "TEXT"),
            ("code", "INTEGER"),
            ("fclass", "TEXT"),
            ("population", "INTEGER"),
            ("name", "TEXT"),
        ],
        "geom_type": "MULTIPOLYGON",
        "expected_min": 500,
    },
    {
        "gpkg_layer": "gis_osm_water_a_free",
        "table": "bronze_location.raw_osm_water_a",
        "fields": list(_BASE),
        "geom_type": "MULTIPOLYGON",
        "expected_min": 30_000,
    },
    {
        "gpkg_layer": "gis_osm_waterways_free",
        "table": "bronze_location.raw_osm_waterways",
        "fields": [
            ("osm_id", "TEXT"),
            ("code", "INTEGER"),
            ("fclass", "TEXT"),
            ("width", "INTEGER"),
            ("name", "TEXT"),
        ],
        "geom_type": "LINESTRING",
        "expected_min": 80_000,
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
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="s09_osm_bronze_load",
        description="Load OSM Portugal layers from MinIO into PostGIS bronze tables",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["osm", "bronze", "pois", "transport", "roads", "postgis"],
    )
    def osm_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Download the latest OSM GPKG from MinIO to a temp directory."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            objects = list(client.list_objects("raw", prefix="osm/", recursive=True))
            gpkg_objects = [o for o in objects if o.object_name.endswith(".gpkg")]
            if not gpkg_objects:
                raise RuntimeError("No OSM GPKG found in MinIO at raw/osm/")

            latest = sorted(gpkg_objects, key=lambda o: o.object_name)[-1]
            log.info("[osm] Latest GPKG in MinIO: %s (%.1f MB)", latest.object_name, latest.size / 1e6)

            tmp_dir = tempfile.mkdtemp(prefix="osm_bronze_")
            local_path = os.path.join(tmp_dir, "osm.gpkg")
            client.fget_object("raw", latest.object_name, local_path)

            file_size = os.path.getsize(local_path)
            log.info("[osm] Downloaded to %s (%.1f MB)", local_path, file_size / 1e6)

            return {"gpkg_path": local_path, "tmp_dir": tmp_dir, "minio_object": latest.object_name}

        @task()
        def create_tables(fetch_result: dict) -> dict:
            """Create all bronze tables if they don't exist."""
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
                        geom GEOMETRY({layer['geom_type']}, 4326),
                        _load_timestamp TIMESTAMPTZ DEFAULT NOW()
                    )
                """
                cur.execute(ddl)
                log.info("[osm] Ensured table %s exists", schema_table)

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

            log.info("[osm] Reading layer %s from %s", gpkg_layer, gpkg_path)
            result = raw_read(gpkg_path, layer=gpkg_layer)
            # raw_read returns (meta, fids, geometry, field_data)
            geometry = result[2]
            field_data = result[3]

            n_features = len(geometry)
            log.info("[osm] Read %d features from %s", n_features, gpkg_layer)

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
                f"VALUES ({placeholders}, ST_GeomFromWKB(%s, 4326))"
            )

            # Insert in batches
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

                if total_inserted % 50_000 == 0 or total_inserted == n_features:
                    log.info("[osm] %s: inserted %d / %d rows", gpkg_layer, total_inserted, n_features)

            conn.commit()
            cur.close()
            conn.close()

            log.info("[osm] Loaded %d rows into %s", n_features, schema_table)
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
                log.info("[osm] %s: %d rows (>= %d OK)", layer["table"], count, expected_min)
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
                log.info("[osm] Cleaned up %s", tmp_dir)

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
            conf={"select": "stg_osm_pois+ stg_osm_transport+"},
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return osm_bronze_load()


dag = _create_dag()
