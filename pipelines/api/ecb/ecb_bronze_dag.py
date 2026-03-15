"""
ECB Bronze Loading — S17

Loads ECB Euribor SDMX JSON from MinIO into PostGIS bronze table.
One row per (series × observation period) in bronze_macro.raw_ecb.

Source-oriented: flattens SDMX observations but stores values as-is.
All business transformation belongs in the silver/dbt layer.

Idempotent: DELETE WHERE series_key = X before INSERT for each series.

To trigger: Airflow UI → ecb_bronze_load → Trigger DAG
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# Series keys — kept in sync with ecb_config.py
SERIES_KEYS = [
    "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
    "M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA",
    "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA",
]

SERIES_NAMES = {
    "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA": "euribor_3m",
    "M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA": "euribor_6m",
    "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA": "euribor_12m",
}


def _flatten_sdmx(raw_json: dict, series_key: str, batch_id: str) -> list[tuple]:
    """
    Flatten SDMX-JSON response into one row per observation period.

    Extracts values directly from the SDMX structure without transformation:
      dataSets[0].series["0:0:0:0:0:0:0"].observations → {idx: [value, ...attrs]}
      structure.dimensions.observation[0].values         → date labels
      structure.dimensions.series[*].values              → series dimension values
      structure.attributes.series[*].values              → series-level attributes
      structure.attributes.observation[*].values         → observation-level attr labels
    """
    datasets = raw_json.get("dataSets", [])
    structure = raw_json.get("structure", {})

    if not datasets or not structure:
        log.warning("[ecb] Empty SDMX response for %s", series_key)
        return []

    # Observation date dimension
    obs_dimensions = structure.get("dimensions", {}).get("observation", [])
    if not obs_dimensions:
        return []
    date_values = obs_dimensions[0].get("values", [])

    # Series-level attributes (unit, decimals, title, etc.)
    series_attr_defs = structure.get("attributes", {}).get("series", [])

    # Observation-level attribute definitions
    obs_attr_defs = structure.get("attributes", {}).get("observation", [])

    # Series data — one series per file
    all_series = datasets[0].get("series", {})
    if not all_series:
        return []

    series_data = next(iter(all_series.values()))
    observations = series_data.get("observations", {})
    series_attrs = series_data.get("attributes", [])

    series_name = SERIES_NAMES.get(series_key, series_key)

    # Extract unit from series attributes
    unit = None
    for i, attr_def in enumerate(series_attr_defs):
        if attr_def.get("id") == "UNIT" and i < len(series_attrs):
            attr_idx = series_attrs[i]
            if attr_idx is not None:
                vals = attr_def.get("values", [])
                if attr_idx < len(vals):
                    unit = vals[attr_idx].get("id")

    rows = []
    for obs_idx_str, obs_values in observations.items():
        obs_idx = int(obs_idx_str)
        if obs_idx >= len(date_values):
            continue

        time_period = date_values[obs_idx].get("id")  # e.g. "1999-01"
        value = obs_values[0] if obs_values else None

        # Observation attributes (OBS_STATUS, OBS_CONF, etc.)
        obs_status = None
        obs_conf = None
        for i, attr_def in enumerate(obs_attr_defs):
            attr_val_idx = obs_values[i + 1] if (i + 1) < len(obs_values) else None
            if attr_val_idx is None:
                continue
            vals = attr_def.get("values", [])
            if attr_val_idx >= len(vals):
                continue
            attr_id = attr_def.get("id")
            if attr_id == "OBS_STATUS":
                obs_status = vals[attr_val_idx].get("id")
            elif attr_id == "OBS_CONF":
                obs_conf = vals[attr_val_idx].get("id")

        rows.append((
            batch_id,
            series_key,
            series_name,
            time_period,
            value,
            unit,
            obs_status,
            obs_conf,
        ))

    return rows


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
        dag_id="ecb_bronze_load",
        description="Load ECB Euribor SDMX JSON from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["ecb", "bronze", "euribor", "postgis"],
    )
    def ecb_bronze_load():

        @task()
        def list_minio_files() -> dict:
            """Find the latest JSON file per series key in MinIO."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            latest_files = {}
            for key in SERIES_KEYS:
                objects = list(
                    client.list_objects("raw", prefix=f"ecb/{key}/", recursive=True)
                )
                json_objects = [o for o in objects if o.object_name.endswith(".json")]
                if json_objects:
                    latest = sorted(json_objects, key=lambda o: o.object_name)[-1]
                    latest_files[key] = latest.object_name
                    log.info(
                        "[ecb] %s → %s (%.1f KB)",
                        key, latest.object_name, latest.size / 1024,
                    )
                else:
                    log.warning("[ecb] No JSON found for series %s", key)

            log.info(
                "[ecb] Found %d / %d series files",
                len(latest_files), len(SERIES_KEYS),
            )
            return latest_files

        @task()
        def create_table() -> None:
            """Create bronze_macro.raw_ecb if it doesn't exist."""
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

            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze_macro")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bronze_macro.raw_ecb (
                    id                BIGSERIAL PRIMARY KEY,

                    -- Metadata
                    _ingested_at      TIMESTAMPTZ DEFAULT NOW(),
                    _source           VARCHAR(30) DEFAULT 'ecb_sdmx',
                    _batch_id         VARCHAR(50),

                    -- Series identity
                    series_key        VARCHAR(100) NOT NULL,
                    series_name       VARCHAR(50),

                    -- Observation (one row per period)
                    time_period       VARCHAR(20) NOT NULL,
                    value             NUMERIC(12,7),
                    unit              VARCHAR(20),

                    -- SDMX observation attributes (raw)
                    obs_status        VARCHAR(10),
                    obs_conf          VARCHAR(10)
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_ecb_series_key ON bronze_macro.raw_ecb(series_key)",
                "CREATE INDEX IF NOT EXISTS idx_ecb_series_period ON bronze_macro.raw_ecb(series_key, time_period)",
            ]:
                cur.execute(idx_sql)

            log.info("[ecb] Ensured bronze_macro.raw_ecb exists with indexes")
            cur.close()
            conn.close()

        @task()
        def load_series(latest_files: dict) -> dict:
            """Flatten SDMX JSON and load into bronze_macro.raw_ecb."""
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            insert_sql = """
                INSERT INTO bronze_macro.raw_ecb (
                    _batch_id, series_key, series_name,
                    time_period, value, unit,
                    obs_status, obs_conf
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

            results = {}
            total_rows = 0

            for series_key, object_name in latest_files.items():
                resp = client.get_object("raw", object_name)
                raw_data = json.loads(resp.read())
                resp.close()
                resp.release_conn()

                # Idempotent: delete existing rows for this series
                cur.execute(
                    "DELETE FROM bronze_macro.raw_ecb WHERE series_key = %s",
                    (series_key,),
                )

                rows = _flatten_sdmx(raw_data, series_key, batch_id)

                if not rows:
                    log.warning("[ecb] %s: no observations to load", series_key)
                    results[series_key] = 0
                    continue

                psycopg2.extras.execute_batch(
                    cur, insert_sql, rows, page_size=1000
                )
                conn.commit()
                total_rows += len(rows)
                results[series_key] = len(rows)
                log.info("[ecb] %s: loaded %d rows", series_key, len(rows))

            cur.close()
            conn.close()

            log.info("[ecb] Total: %d rows across %d series", total_rows, len(results))
            return results

        @task()
        def validate_counts(load_results: dict) -> dict:
            """Verify every series has rows in the table."""
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

            cur.execute("""
                SELECT series_key, COUNT(*),
                       MIN(time_period), MAX(time_period)
                FROM bronze_macro.raw_ecb
                GROUP BY series_key
                ORDER BY series_key
            """)
            series_info = cur.fetchall()

            cur.execute("SELECT COUNT(*) FROM bronze_macro.raw_ecb")
            total = cur.fetchone()[0]

            cur.close()
            conn.close()

            loaded_keys = set()
            for key, count, min_period, max_period in series_info:
                loaded_keys.add(key)
                log.info(
                    "[ecb] %s: %d rows (%s → %s)",
                    key, count, min_period, max_period,
                )

            missing = [k for k in SERIES_KEYS if k not in loaded_keys]
            if missing:
                log.warning(
                    "[ecb] %d series missing: %s", len(missing), missing
                )

            log.info("[ecb] Total rows in bronze_macro.raw_ecb: %d", total)
            return {
                "total_rows": total,
                "series_loaded": len(loaded_keys),
                "missing": missing,
            }

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_series(files)
        table_ready >> loaded
        validated = validate_counts(loaded)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_ecb_build",
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return ecb_bronze_load()


dag = _create_dag()
