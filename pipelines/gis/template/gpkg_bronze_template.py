"""
GPKG Bronze Loading Template — Flow C

Factory that creates Airflow DAGs for loading GeoPackage files from MinIO
into PostGIS bronze tables. Handles single-layer and multi-layer GPKGs
with configurable batch sizes for large datasets.

Reusable across: CAOP, BGRI, OSM, COS, and any future GPKG source.

Pipeline: MinIO (raw GPKG) → PostGIS (bronze table) → trigger dbt build

--- Usage ---

1. Define a GpkgBronzeConfig with your layers, table names, and fields.
2. Call create_gpkg_bronze_dag(config) to get a ready-to-register Airflow DAG.

Example:
    from pipelines.gis.template.gpkg_bronze_template import (
        GpkgBronzeConfig, GpkgLayerConfig, create_gpkg_bronze_dag,
    )

    COS_BRONZE_CONFIG = GpkgBronzeConfig(
        dag_id="cos2023_bronze_load",
        source_name="cos",
        minio_prefix="cos",
        layers=[
            GpkgLayerConfig(
                gpkg_layer=None,  # auto-detect single layer
                table="bronze_geo.raw_cos2023",
                fields=[("objectid", "INTEGER"), ...],
                geom_type="POLYGON",
                expected_min=500_000,
            ),
        ],
        dbt_trigger_dag_id="dbt_cos_build",
    )
    dag = create_gpkg_bronze_dag(COS_BRONZE_CONFIG)
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpkgLayerConfig:
    """Configuration for a single GPKG layer → bronze table mapping.

    When gpkg_layer is None, the template auto-detects the first layer
    in the GPKG file (useful for single-layer files like COS or BGRI).
    """

    gpkg_layer: Optional[str]  # GPKG layer name, or None for auto-detect
    table: str  # Target bronze table (schema-qualified)
    fields: list[tuple[str, str]]  # [(column_name, SQL_TYPE), ...]
    geom_type: str  # PostGIS geometry type: POLYGON, MULTIPOLYGON, POINT, ...
    expected_min: int  # Minimum expected row count for validation
    srid: int = 3763  # Source SRID (default: PT-TM06/ETRS89)
    indexes: list[str] = field(default_factory=list)  # Extra index columns


@dataclass
class GpkgBronzeConfig:
    """All parameters needed to instantiate a GPKG bronze loading DAG."""

    # --- DAG identity ---
    dag_id: str
    source_name: str  # Short identifier for logs — e.g. "cos", "caop"
    description: str = ""

    # --- MinIO source ---
    minio_bucket: str = "raw"
    minio_prefix: str = ""  # e.g. "cos" → looks for raw/cos/**/*.gpkg

    # --- Layers ---
    layers: list[GpkgLayerConfig] = field(default_factory=list)

    # --- Loading ---
    read_batch_size: int = 5000  # Features per pyogrio read batch
    insert_page_size: int = 500  # Rows per execute_batch page

    # --- Downstream ---
    dbt_trigger_dag_id: Optional[str] = None  # DAG to trigger after loading

    # --- DAG settings ---
    tags: list[str] = field(default_factory=list)
    retries: int = 1
    retry_delay_minutes: int = 2


# ---------------------------------------------------------------------------
# DAG factory
# ---------------------------------------------------------------------------


def create_gpkg_bronze_dag(config: GpkgBronzeConfig):
    """
    Returns an Airflow DAG that loads GPKG layers from MinIO into PostGIS.

    Task graph:
        fetch_from_minio
              ↓
        create_tables
              ↓
        load_layer (per layer, sequential for multi-layer)
              ↓
        validate_counts
           ↙      ↘
      cleanup   trigger_dbt (optional)
    """
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": config.retries,
        "retry_delay": timedelta(minutes=config.retry_delay_minutes),
    }

    @dag(
        dag_id=config.dag_id,
        description=config.description or f"Load {config.source_name} GPKG from MinIO into PostGIS",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["bronze", "postgis"] + config.tags,
    )
    def gpkg_bronze_load():

        @task()
        def fetch_from_minio() -> dict:
            """Download the latest GPKG from MinIO to a temp directory."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            objects = list(
                client.list_objects(config.minio_bucket, prefix=f"{config.minio_prefix}/", recursive=True)
            )
            gpkg_objects = [o for o in objects if o.object_name.endswith(".gpkg")]
            if not gpkg_objects:
                raise RuntimeError(
                    f"No GPKG found in MinIO at {config.minio_bucket}/{config.minio_prefix}/"
                )

            latest = sorted(gpkg_objects, key=lambda o: o.object_name)[-1]
            log.info(
                "[%s] Latest GPKG in MinIO: %s (%.1f MB)",
                config.source_name, latest.object_name, latest.size / 1e6,
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"{config.source_name}_bronze_")
            local_path = os.path.join(tmp_dir, f"{config.source_name}.gpkg")
            client.fget_object(config.minio_bucket, latest.object_name, local_path)

            file_size = os.path.getsize(local_path)
            log.info("[%s] Downloaded to %s (%.1f MB)", config.source_name, local_path, file_size / 1e6)

            return {"gpkg_path": local_path, "tmp_dir": tmp_dir, "minio_object": latest.object_name}

        @task()
        def resolve_layers(fetch_result: dict) -> dict:
            """Resolve auto-detect layer names and return enriched config."""
            import pyogrio

            gpkg_path = fetch_result["gpkg_path"]
            raw_layers = pyogrio.list_layers(gpkg_path)
            available = [row[0] for row in raw_layers]

            log.info("[%s] Layers found in GPKG: %s", config.source_name, available)

            resolved = []
            for layer_cfg in config.layers:
                layer_name = layer_cfg.gpkg_layer
                if layer_name is None:
                    if not available:
                        raise RuntimeError(f"No layers found in {gpkg_path}")
                    layer_name = available[0]
                    log.info(
                        "[%s] Auto-detected layer '%s' for table %s",
                        config.source_name, layer_name, layer_cfg.table,
                    )
                elif layer_name not in available:
                    raise ValueError(
                        f"[{config.source_name}] Expected layer '{layer_name}' not found. "
                        f"Available: {available}"
                    )

                info = pyogrio.read_info(gpkg_path, layer=layer_name)
                n_features = info.get("features", 0)
                log.info(
                    "[%s] Layer '%s': %d features",
                    config.source_name, layer_name, n_features,
                )

                resolved.append({
                    "gpkg_layer": layer_name,
                    "table": layer_cfg.table,
                    "n_features": n_features,
                    "layer_index": len(resolved),
                })

            fetch_result["resolved_layers"] = resolved
            return fetch_result

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

            for layer_cfg in config.layers:
                cols = ", ".join(f"{name} {dtype}" for name, dtype in layer_cfg.fields)
                ddl = f"""
                    CREATE TABLE IF NOT EXISTS {layer_cfg.table} (
                        {cols},
                        geom GEOMETRY({layer_cfg.geom_type}, {layer_cfg.srid}),
                        _load_timestamp TIMESTAMPTZ DEFAULT NOW()
                    )
                """
                cur.execute(ddl)

                # GIST index on geometry
                idx_base = layer_cfg.table.replace(".", "_")
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{idx_base}_geom "
                    f"ON {layer_cfg.table} USING GIST(geom)"
                )

                # Extra indexes
                for col in layer_cfg.indexes:
                    cur.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{idx_base}_{col} "
                        f"ON {layer_cfg.table} ({col})"
                    )

                log.info("[%s] Ensured table %s exists", config.source_name, layer_cfg.table)

            cur.close()
            conn.close()
            return fetch_result

        @task()
        def load_layer(fetch_result: dict, layer_index: int) -> dict:
            """Load a single GPKG layer into its bronze table with batched reads."""
            import psycopg2
            import psycopg2.extras
            from pyogrio.raw import read as raw_read
            from airflow.models import Variable

            layer_cfg = config.layers[layer_index]
            resolved = fetch_result["resolved_layers"][layer_index]
            gpkg_path = fetch_result["gpkg_path"]
            gpkg_layer = resolved["gpkg_layer"]
            schema_table = layer_cfg.table
            field_names = [name for name, _ in layer_cfg.fields]
            n_features = resolved["n_features"]

            log.info(
                "[%s] Loading layer '%s' (%d features) into %s",
                config.source_name, gpkg_layer, n_features, schema_table,
            )

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
                f"VALUES ({placeholders}, ST_GeomFromWKB(%s, {layer_cfg.srid}))"
            )

            # Read and insert in batches
            total_inserted = 0
            batch_size = config.read_batch_size

            for start in range(0, n_features, batch_size):
                result = raw_read(
                    gpkg_path,
                    layer=gpkg_layer,
                    skip_features=start,
                    max_features=batch_size,
                )
                geometry = result[2]
                field_data = result[3]

                count = len(geometry)
                if count == 0:
                    break

                rows = []
                for i in range(count):
                    field_values = []
                    for j in range(len(field_names)):
                        val = field_data[j][i]
                        if hasattr(val, "item"):
                            val = val.item()
                        field_values.append(val)
                    wkb = bytes(geometry[i])
                    field_values.append(wkb)
                    rows.append(tuple(field_values))

                psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=config.insert_page_size)
                conn.commit()

                total_inserted += count
                log.info("[%s] Inserted %d / %d features", config.source_name, total_inserted, n_features)

            cur.close()
            conn.close()

            log.info("[%s] Loaded %d rows into %s", config.source_name, total_inserted, schema_table)
            return {"table": schema_table, "rows_loaded": total_inserted}

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
            for layer_cfg in config.layers:
                cur.execute(f"SELECT COUNT(*) FROM {layer_cfg.table}")
                count = cur.fetchone()[0]
                if count < layer_cfg.expected_min:
                    raise ValueError(
                        f"{layer_cfg.table}: got {count} rows, expected >= {layer_cfg.expected_min}"
                    )
                log.info(
                    "[%s] %s: %d rows (>= %d OK)",
                    config.source_name, layer_cfg.table, count, layer_cfg.expected_min,
                )
                results[layer_cfg.table] = count

            cur.close()
            conn.close()
            return results

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, validation: dict):
            """Remove temp directory after all loads complete."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[%s] Cleaned up %s", config.source_name, tmp_dir)

        # --- Task wiring ---
        fetched = fetch_from_minio()
        resolved = resolve_layers(fetched)
        tables_ready = create_tables(resolved)

        load_results = []
        prev = tables_ready
        for i in range(len(config.layers)):
            result = load_layer(prev, i)
            load_results.append(result)
            prev = result  # sequential layer loading

        validated = validate_counts(load_results)
        cleanup_temp(fetched, validated)

        if config.dbt_trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_dbt = TriggerDagRunOperator(
                task_id="trigger_dbt_pipeline",
                trigger_dag_id=config.dbt_trigger_dag_id,
                wait_for_completion=True,
                reset_dag_run=True,
                poke_interval=10,
            )
            validated >> trigger_dbt

    return gpkg_bronze_load()
