"""
Eurostat Bronze Loading — S18

Loads Eurostat JSON-stat 2.0 files from MinIO into PostGIS bronze table.
One row per (purchase × unit × geo × time_period) in bronze_macro.raw_eurostat.

Source-oriented: unrolls JSON-stat cube dimensions into tabular rows.
Values stored as-is from the API. All business transformation belongs in silver/dbt.

Idempotent: DELETE WHERE dataset_code = X before INSERT.

To trigger: Airflow UI → eurostat_bronze_load → Trigger DAG
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def _flatten_eurostat_jsonstat(
    raw_json: dict, dataset_code: str, batch_id: str
) -> list[tuple]:
    """
    Flatten a Eurostat JSON-stat 2.0 response into rows for INSERT.

    Eurostat JSON-stat has NO extension.series — observations are purely
    indexed by row-major position across dimensions (freq × purchase × unit
    × geo × time).

    For each combination of non-time dimensions, iterate time periods and
    look up value[flat_idx] where flat_idx is the row-major index.
    """
    dim_ids = raw_json.get("id", [])
    dim_sizes = raw_json.get("size", [])
    raw_values = raw_json.get("value", {})
    raw_statuses = raw_json.get("status", {})
    dimensions = raw_json.get("dimension", {})

    if not dim_ids or not dim_sizes or not raw_values:
        log.warning("[eurostat] Empty JSON-stat response for %s", dataset_code)
        return []

    # JSON-stat 2.0 allows value/status as list (dense) or dict (sparse).
    # Normalize both to dict[int, value] for uniform access.
    if isinstance(raw_values, list):
        values = {i: v for i, v in enumerate(raw_values) if v is not None}
    else:
        values = {int(k): v for k, v in raw_values.items()}

    if isinstance(raw_statuses, list):
        statuses = {i: v for i, v in enumerate(raw_statuses) if v is not None}
    else:
        statuses = {int(k): v for k, v in raw_statuses.items()}

    # Build category code lists for each dimension (ordered by index position)
    dim_codes: dict[str, list[str]] = {}
    for dim_id in dim_ids:
        dim_def = dimensions.get(dim_id, {})
        cat = dim_def.get("category", {})
        idx = cat.get("index", {})
        if isinstance(idx, dict):
            dim_codes[dim_id] = sorted(idx.keys(), key=lambda k: idx[k])
        elif isinstance(idx, list):
            dim_codes[dim_id] = list(idx)
        else:
            dim_codes[dim_id] = []

    # Compute strides for row-major indexing
    # stride[i] = product of sizes[i+1] * sizes[i+2] * ...
    n_dims = len(dim_sizes)
    strides = [1] * n_dims
    for i in range(n_dims - 2, -1, -1):
        strides[i] = strides[i + 1] * dim_sizes[i + 1]

    # Find the time dimension (last dimension by convention in Eurostat)
    time_dim_id = "time"
    if time_dim_id not in dim_ids:
        # Fallback: check role
        role = raw_json.get("role", {})
        time_roles = role.get("time", [])
        time_dim_id = time_roles[0] if time_roles else dim_ids[-1]

    time_dim_idx = dim_ids.index(time_dim_id)
    time_codes = dim_codes[time_dim_id]

    # Identify non-time dimensions and their positions
    non_time_dims = [
        (i, dim_id) for i, dim_id in enumerate(dim_ids) if dim_id != time_dim_id
    ]

    rows = []

    def _recurse(dim_pos: int, current_offset: int, current_codes: dict):
        """Recursively iterate non-time dimensions, then sweep time."""
        if dim_pos >= len(non_time_dims):
            # All non-time dims fixed — iterate time
            freq = current_codes.get("freq", "Q")
            purchase = current_codes.get("purchase", "")
            unit = current_codes.get("unit", "")
            geo = current_codes.get("geo", "")

            for t_idx, time_code in enumerate(time_codes):
                flat_idx = current_offset + t_idx * strides[time_dim_idx]

                if flat_idx not in values:
                    continue

                value = values[flat_idx]
                status = statuses.get(flat_idx)

                rows.append((
                    batch_id,
                    dataset_code,
                    freq,
                    purchase,
                    unit,
                    geo,
                    time_code,
                    value,
                    status,
                ))
            return

        i, dim_id = non_time_dims[dim_pos]
        codes = dim_codes[dim_id]
        for c_idx, code in enumerate(codes):
            new_offset = current_offset + c_idx * strides[i]
            current_codes[dim_id] = code
            _recurse(dim_pos + 1, new_offset, current_codes)

    _recurse(0, 0, {})
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
        dag_id="eurostat_bronze_load",
        description="Load Eurostat JSON-stat from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["eurostat", "bronze", "macro", "postgis"],
    )
    def eurostat_bronze_load():

        @task()
        def list_minio_files() -> dict:
            """Find the latest JSON file per dataset in MinIO."""
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.eurostat.eurostat_config import DATASET_CODES

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            latest_files = {}
            for code in DATASET_CODES:
                objects = list(
                    client.list_objects(
                        "raw", prefix=f"eurostat/{code}/", recursive=True
                    )
                )
                json_objects = [
                    o for o in objects if o.object_name.endswith(".json")
                ]
                if json_objects:
                    latest = sorted(
                        json_objects, key=lambda o: o.object_name
                    )[-1]
                    latest_files[code] = latest.object_name
                    log.info(
                        "[eurostat] %s → %s (%.1f KB)",
                        code, latest.object_name, latest.size / 1024,
                    )
                else:
                    log.warning("[eurostat] No JSON found for %s", code)

            log.info(
                "[eurostat] Found %d / %d dataset files",
                len(latest_files), len(DATASET_CODES),
            )
            return latest_files

        @task()
        def create_table() -> None:
            """Create bronze_macro.raw_eurostat if it doesn't exist."""
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
                CREATE TABLE IF NOT EXISTS bronze_macro.raw_eurostat (
                    id                BIGSERIAL PRIMARY KEY,

                    -- Metadata
                    _ingested_at      TIMESTAMPTZ DEFAULT NOW(),
                    _source           VARCHAR(30) DEFAULT 'eurostat',
                    _batch_id         VARCHAR(50),

                    -- Dataset identity
                    dataset_code      VARCHAR(30) NOT NULL,

                    -- Dimensions (from JSON-stat)
                    freq              CHAR(1) DEFAULT 'Q',
                    purchase          VARCHAR(20) NOT NULL,
                    unit              VARCHAR(20) NOT NULL,
                    geo               VARCHAR(10) NOT NULL,
                    time_period       VARCHAR(10) NOT NULL,

                    -- Observation
                    value             NUMERIC(12,4),
                    status            VARCHAR(10)
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_eurostat_geo_time ON bronze_macro.raw_eurostat(geo, time_period)",
                "CREATE INDEX IF NOT EXISTS idx_eurostat_dataset ON bronze_macro.raw_eurostat(dataset_code)",
            ]:
                cur.execute(idx_sql)

            log.info("[eurostat] Ensured bronze_macro.raw_eurostat exists with indexes")
            cur.close()
            conn.close()

        @task()
        def load_datasets(latest_files: dict) -> dict:
            """Flatten JSON-stat files and load into bronze_macro.raw_eurostat."""
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
                INSERT INTO bronze_macro.raw_eurostat (
                    _batch_id, dataset_code,
                    freq, purchase, unit, geo, time_period,
                    value, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            results = {}
            total_rows = 0

            for dataset_code, object_name in latest_files.items():
                resp = client.get_object("raw", object_name)
                raw_data = json.loads(resp.read())
                resp.close()
                resp.release_conn()

                cur.execute(
                    "DELETE FROM bronze_macro.raw_eurostat WHERE dataset_code = %s",
                    (dataset_code,),
                )

                rows = _flatten_eurostat_jsonstat(raw_data, dataset_code, batch_id)

                if not rows:
                    log.warning("[eurostat] %s: no observations to load", dataset_code)
                    results[dataset_code] = 0
                    continue

                for start in range(0, len(rows), 5000):
                    batch = rows[start : start + 5000]
                    psycopg2.extras.execute_batch(
                        cur, insert_sql, batch, page_size=1000
                    )

                conn.commit()
                total_rows += len(rows)
                results[dataset_code] = len(rows)
                log.info("[eurostat] %s: loaded %d rows", dataset_code, len(rows))

            cur.close()
            conn.close()

            log.info(
                "[eurostat] Total: %d rows across %d datasets",
                total_rows, len(results),
            )
            return results

        @task()
        def validate_counts(load_results: dict) -> dict:
            """Verify datasets have rows in the table."""
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
                SELECT dataset_code, geo, COUNT(*),
                       MIN(time_period), MAX(time_period)
                FROM bronze_macro.raw_eurostat
                WHERE geo IN ('PT', 'ES', 'EU', 'EA')
                GROUP BY dataset_code, geo
                ORDER BY dataset_code, geo
            """)
            geo_info = cur.fetchall()

            cur.execute("SELECT COUNT(*) FROM bronze_macro.raw_eurostat")
            total = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(DISTINCT geo) FROM bronze_macro.raw_eurostat"
            )
            n_geos = cur.fetchone()[0]

            cur.close()
            conn.close()

            for ds, geo, count, min_t, max_t in geo_info:
                log.info(
                    "[eurostat] %s geo=%s: %d rows (%s → %s)",
                    ds, geo, count, min_t, max_t,
                )

            empty = [
                code for code, cnt in load_results.items() if cnt == 0
            ]
            if empty:
                log.warning(
                    "[eurostat] %d datasets with 0 rows: %s", len(empty), empty
                )

            log.info(
                "[eurostat] Total: %d rows, %d geo entities", total, n_geos
            )
            return {
                "total_rows": total,
                "geo_entities": n_geos,
                "empty_datasets": empty,
            }

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_datasets(files)
        table_ready >> loaded
        validated = validate_counts(loaded)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_scoped_build",
            conf={"select": "stg_eurostat+"},
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return eurostat_bronze_load()


dag = _create_dag()
