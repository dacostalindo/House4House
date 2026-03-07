"""
BPStat Bronze Loading — S16

Loads BPStat JSON-stat 2.0 files from MinIO into PostGIS bronze table.
One row per (series × observation period) in bronze_macro.raw_bpstat.

Source-oriented: flattens JSON-stat cube into tabular rows.
Values stored as-is from the API. All business transformation belongs in silver/dbt.

Idempotent: DELETE WHERE dataset_id = X before INSERT per dataset.

To trigger: Airflow UI → bpstat_bronze_load → Trigger DAG
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from functools import reduce
from operator import mul

log = logging.getLogger(__name__)


def _flatten_jsonstat(
    raw_json: dict, dataset_code: str, batch_id: str
) -> list[tuple]:
    """
    Flatten a JSON-stat 2.0 dataset response into rows for INSERT.

    JSON-stat stores observations in a flat dict keyed by row-major index
    across all dimensions. We need to:
    1. Find the time dimension (reference_date)
    2. For each series in extension.series, compute which value indices
       belong to it based on its dimension_category positions
    3. Extract (date, value, status) for each observation
    """
    dim_ids = raw_json.get("id", [])
    dim_sizes = raw_json.get("size", [])
    raw_values = raw_json.get("value", {})
    raw_statuses = raw_json.get("status", {})

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
    dimensions = raw_json.get("dimension", {})
    extension = raw_json.get("extension", {})
    series_list = extension.get("series", [])

    if not dim_ids or not dim_sizes or not values:
        log.warning("[bpstat] Empty JSON-stat response for %s", dataset_code)
        return []

    # Parse domain_id and dataset_id from the code (e.g. "186/datasets/abc123")
    parts = dataset_code.split("/")
    domain_id = int(parts[0]) if parts else None
    dataset_id = parts[2] if len(parts) >= 3 else dataset_code

    # Find the time dimension
    time_dim_id = None
    role = raw_json.get("role", {})
    time_roles = role.get("time", [])
    if time_roles:
        time_dim_id = time_roles[0]
    if not time_dim_id and "reference_date" in dim_ids:
        time_dim_id = "reference_date"

    if not time_dim_id or time_dim_id not in dim_ids:
        log.warning("[bpstat] No time dimension found for %s", dataset_code)
        return []

    time_dim_idx = dim_ids.index(time_dim_id)
    time_dim = dimensions.get(time_dim_id, {})
    time_categories = time_dim.get("category", {})

    # Time category index — can be array or object
    time_index = time_categories.get("index", [])
    if isinstance(time_index, dict):
        # Convert {"2018-12-31": 0, ...} to ordered list
        time_dates = sorted(time_index.keys(), key=lambda k: time_index[k])
    else:
        time_dates = list(time_index)

    num_time_periods = len(time_dates)

    # Build dimension category index maps for non-time dimensions
    dim_category_indices = {}
    for dim_id in dim_ids:
        if dim_id == time_dim_id:
            continue
        dim_def = dimensions.get(dim_id, {})
        cat = dim_def.get("category", {})
        idx = cat.get("index", [])
        if isinstance(idx, dict):
            dim_category_indices[dim_id] = idx
        elif isinstance(idx, list):
            dim_category_indices[dim_id] = {v: i for i, v in enumerate(idx)}
        else:
            dim_category_indices[dim_id] = {}

    # Compute strides for row-major indexing
    # stride[i] = product of sizes[i+1] * sizes[i+2] * ...
    strides = [1] * len(dim_sizes)
    for i in range(len(dim_sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * dim_sizes[i + 1]

    # Find unit dimension if present
    unit_dim_id = None
    metric_roles = role.get("metric", [])
    if metric_roles:
        unit_dim_id = metric_roles[0]

    rows = []

    for series_info in series_list:
        series_id = series_info.get("id")
        series_label = series_info.get("label", "")
        dim_categories = series_info.get("dimension_category", [])

        # Map series dimension categories to index positions
        series_dim_positions = {}
        for dc in dim_categories:
            d_id = str(dc.get("dimension_id", ""))
            c_id = str(dc.get("category_id", ""))
            if d_id in dim_category_indices:
                pos = dim_category_indices[d_id].get(c_id)
                if pos is not None:
                    series_dim_positions[d_id] = pos

        # Compute base offset for this series (non-time dimensions)
        base_offset = 0
        for i, dim_id in enumerate(dim_ids):
            if dim_id == time_dim_id:
                continue
            pos = series_dim_positions.get(dim_id, 0)
            base_offset += pos * strides[i]

        # Extract unit from the series label or dimension
        unit = None
        if unit_dim_id and unit_dim_id in dim_ids:
            unit_dim = dimensions.get(unit_dim_id, {})
            unit_cat = unit_dim.get("category", {})
            unit_labels = unit_cat.get("label", {})
            # Find which unit category this series uses
            for dc in dim_categories:
                if str(dc.get("dimension_id", "")) == unit_dim_id:
                    c_id = str(dc.get("category_id", ""))
                    unit = unit_labels.get(c_id, c_id)
                    break

        time_stride = strides[time_dim_idx]

        for t_idx in range(num_time_periods):
            flat_idx = base_offset + t_idx * time_stride

            if flat_idx not in values:
                continue

            value = values[flat_idx]
            status = statuses.get(flat_idx)
            period = time_dates[t_idx]

            rows.append((
                batch_id,
                domain_id,
                dataset_id,
                series_id,
                series_label,
                period,
                value,
                unit,
                status,
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
        dag_id="bpstat_bronze_load",
        description="Load BPStat JSON-stat from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["bpstat", "bronze", "macro", "postgis"],
    )
    def bpstat_bronze_load():

        @task()
        def list_minio_files() -> dict:
            """Find the latest JSON file per dataset in MinIO."""
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.bpstat.bpstat_config import DATASET_CODES

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
                        "raw", prefix=f"bpstat/{code}/", recursive=True
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
                        "[bpstat] %s → %s (%.1f KB)",
                        code, latest.object_name, latest.size / 1024,
                    )
                else:
                    log.warning("[bpstat] No JSON found for %s", code)

            log.info(
                "[bpstat] Found %d / %d dataset files",
                len(latest_files), len(DATASET_CODES),
            )
            return latest_files

        @task()
        def create_table() -> None:
            """Create bronze_macro.raw_bpstat if it doesn't exist."""
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
                CREATE TABLE IF NOT EXISTS bronze_macro.raw_bpstat (
                    id                BIGSERIAL PRIMARY KEY,

                    -- Metadata
                    _ingested_at      TIMESTAMPTZ DEFAULT NOW(),
                    _source           VARCHAR(30) DEFAULT 'bpstat',
                    _batch_id         VARCHAR(50),

                    -- Dataset identity
                    domain_id         INTEGER,
                    dataset_id        VARCHAR(50),

                    -- Series identity
                    series_id         INTEGER NOT NULL,
                    series_name       TEXT,

                    -- Observation
                    period            VARCHAR(20) NOT NULL,
                    value             NUMERIC(20,6),
                    unit              VARCHAR(100),
                    status            VARCHAR(10)
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_bpstat_series_id ON bronze_macro.raw_bpstat(series_id)",
                "CREATE INDEX IF NOT EXISTS idx_bpstat_dataset ON bronze_macro.raw_bpstat(dataset_id)",
                "CREATE INDEX IF NOT EXISTS idx_bpstat_series_period ON bronze_macro.raw_bpstat(series_id, period)",
            ]:
                cur.execute(idx_sql)

            log.info("[bpstat] Ensured bronze_macro.raw_bpstat exists with indexes")
            cur.close()
            conn.close()

        @task()
        def load_datasets(latest_files: dict) -> dict:
            """Flatten JSON-stat files and load into bronze_macro.raw_bpstat."""
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
                INSERT INTO bronze_macro.raw_bpstat (
                    _batch_id, domain_id, dataset_id,
                    series_id, series_name,
                    period, value, unit, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            results = {}
            total_rows = 0

            for dataset_code, object_name in latest_files.items():
                resp = client.get_object("raw", object_name)
                raw_data = json.loads(resp.read())
                resp.close()
                resp.release_conn()

                # Extract dataset_id for idempotent delete
                parts = dataset_code.split("/")
                dataset_id = parts[2] if len(parts) >= 3 else dataset_code

                cur.execute(
                    "DELETE FROM bronze_macro.raw_bpstat WHERE dataset_id = %s",
                    (dataset_id,),
                )

                rows = _flatten_jsonstat(raw_data, dataset_code, batch_id)

                if not rows:
                    log.warning("[bpstat] %s: no observations to load", dataset_code)
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
                log.info("[bpstat] %s: loaded %d rows", dataset_code, len(rows))

            cur.close()
            conn.close()

            log.info(
                "[bpstat] Total: %d rows across %d datasets",
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
                SELECT domain_id, dataset_id, COUNT(*),
                       COUNT(DISTINCT series_id),
                       MIN(period), MAX(period)
                FROM bronze_macro.raw_bpstat
                GROUP BY domain_id, dataset_id
                ORDER BY domain_id, dataset_id
            """)
            dataset_info = cur.fetchall()

            cur.execute("SELECT COUNT(*) FROM bronze_macro.raw_bpstat")
            total = cur.fetchone()[0]

            cur.close()
            conn.close()

            for domain, ds_id, count, n_series, min_p, max_p in dataset_info:
                log.info(
                    "[bpstat] domain=%s dataset=%s: %d rows, %d series (%s → %s)",
                    domain, ds_id[:12], count, n_series, min_p, max_p,
                )

            empty = [
                code for code, cnt in load_results.items() if cnt == 0
            ]
            if empty:
                log.warning("[bpstat] %d datasets with 0 rows: %s", len(empty), empty)

            log.info("[bpstat] Total rows in bronze_macro.raw_bpstat: %d", total)
            return {
                "total_rows": total,
                "datasets_loaded": len(dataset_info),
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
            conf={"select": "stg_bpstat+"},
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        validated >> trigger_dbt

    return bpstat_bronze_load()


dag = _create_dag()
