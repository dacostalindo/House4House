"""
DGT LiDAR Aveiro Ingestion — omnibus DAG (2m only)

Iterates over LIDAR_LAYERS in lidar_config.py (MDT-2m + MDS-2m) and fetches
each layer via the unified DgtStacAdapter from WS1. Per-tile GeoTIFFs land
in MinIO under `raw/lidar/{COLLECTION}/{YYYYMMDD}/{tile_id}.tif`, plus a
manifest.json per collection.

Trigger manually from Airflow UI; optional `layer_filter` param matches the
SRUP/LNEG omnibus convention.

DGT_CDD_COOKIE: Keycloak session cookie stored in Airflow Variable. Must be
refreshed manually until v2 hardening lands a Selenium-based cookie cron.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import timedelta

from pipelines.gis.lidar.lidar_config import (
    LIDAR_CONFIG,
    LIDAR_LAYERS,
    MINIO_BUCKET,
    minio_prefix_for,
)

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    cfg = LIDAR_CONFIG

    default_args = {
        "owner": "data-engineering",
        "retries": cfg.retries,
        "retry_delay": timedelta(minutes=cfg.retry_delay_minutes),
    }

    @dag(
        dag_id=cfg.ingestion_dag_id,
        description=cfg.description_ingestion,
        schedule=cfg.schedule,
        start_date=cfg.start_date,
        catchup=False,
        default_args=default_args,
        max_active_runs=cfg.max_active_runs,
        max_active_tasks=cfg.max_active_tasks,
        tags=["ingestion", "gis", "minio", "dgt_stac"] + cfg.tags,
        params={
            "layer_filter": Param(
                default="",
                description=(
                    "Optional comma-separated list of layer names to ingest "
                    "(e.g. 'lidar_mdt_2m'). Empty = ingest all."
                ),
                type="string",
            ),
        },
    )
    def lidar_aveiro_ingestion():
        @task()
        def select_layers(**context) -> list[dict]:
            raw = context["params"].get("layer_filter", "").strip()
            if raw:
                wanted = {n.strip() for n in raw.split(",") if n.strip()}
            else:
                wanted = set()

            selected: list[dict] = []
            for layer in LIDAR_LAYERS:
                if wanted and layer.name not in wanted:
                    continue
                selected.append(
                    {
                        "name": layer.name,
                        "collection_id": layer.collection_id,
                        "label": layer.label,
                        "expected_min_features": layer.expected_min_features,
                    }
                )

            log.info("[lidar] selected layers: %s", [s["name"] for s in selected])

            if not selected:
                raise ValueError(
                    f"No layers matched filter '{raw}'. Available: {[layer.name for layer in LIDAR_LAYERS]}"
                )

            return selected

        @task()
        def fetch_one_layer(layer_meta: dict) -> dict:
            """Fetch one LiDAR collection via DgtStacAdapter + upload tiles to MinIO.

            DgtStacAdapter handles STAC search pagination + cookie-gated tile
            downloads. Each layer runs as its own dynamically-mapped task so a
            failure on one collection doesn't block the other.
            """
            from pipelines.common.minio_upload import upload_files_to_minio
            from pipelines.gis.template.ingestion_template import (
                DgtStacAdapter,
                UnifiedIngestionConfig,
            )

            layer_cfg = next(
                (layer for layer in LIDAR_LAYERS if layer.name == layer_meta["name"]),
                None,
            )
            if layer_cfg is None:
                raise ValueError(f"Unknown layer name: {layer_meta['name']}")

            adapter_cfg = UnifiedIngestionConfig(
                dag_id=f"_inline_{layer_cfg.name}",
                source_name=layer_cfg.name,
                description=layer_cfg.label,
                protocol="dgt_stac",
                endpoint_url=cfg.stac_root,
                collection_id=layer_cfg.collection_id,
                page_size=cfg.page_size,
                request_delay_seconds=cfg.request_delay_seconds,
                request_timeout_seconds=cfg.request_timeout_seconds,
                bbox_4326=cfg.aveiro_bbox_4326,
                auth_cookie_variable=cfg.auth_cookie_variable,
                minio_prefix=minio_prefix_for(layer_cfg),
                bronze_schema_table=layer_cfg.bronze_table,
            )

            log.info(
                "[%s] adapter cfg: stac_root=%s collection=%s bbox=%s",
                layer_cfg.name,
                cfg.stac_root,
                layer_cfg.collection_id,
                cfg.aveiro_bbox_4326,
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"lidar_{layer_cfg.name}_")
            try:
                adapter = DgtStacAdapter(adapter_cfg)
                probe = adapter.probe()
                log.info("[%s] STAC probe: %s", layer_cfg.name, probe)

                meta = adapter.fetch_to(tmp_dir)
                log.info(
                    "[%s] fetched %d tiles in %d STAC pages (%.1f MB)",
                    layer_cfg.name,
                    meta["feature_count"],
                    meta["pages"],
                    meta["bytes"] / 1000000.0,
                )

                if meta["feature_count"] < layer_cfg.expected_min_features:
                    raise ValueError(
                        f"[{layer_cfg.name}] only {meta['feature_count']} tiles "
                        f"returned, expected >= {layer_cfg.expected_min_features}"
                    )

                upload = upload_files_to_minio(
                    files=meta["files"],
                    bucket=MINIO_BUCKET,
                    prefix=minio_prefix_for(layer_cfg),
                    source_name=layer_cfg.name,
                    tmp_dir=tmp_dir,
                )
                base_prefix = f"{minio_prefix_for(layer_cfg)}/{upload['date_str']}"
                manifest_object = next(
                    (obj for obj in upload["uploaded"] if obj.endswith("manifest.json")),
                    None,
                )

                return {
                    "name": layer_cfg.name,
                    "collection_id": layer_cfg.collection_id,
                    "feature_count": meta["feature_count"],
                    "uploaded_count": len(upload["uploaded"]),
                    "uploaded_bytes": upload["bytes"],
                    "manifest_object": manifest_object,
                    "minio_prefix": base_prefix,
                }
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(results: list[dict]) -> dict:
            total = 0
            total_bytes = 0
            for r in results:
                total += r["feature_count"]
                total_bytes += r.get("uploaded_bytes", 0)
                log.info(
                    "[lidar] %s: %d tiles uploaded (%.1f MB)",
                    r["name"],
                    r["feature_count"],
                    r.get("uploaded_bytes", 0) / 1000000.0,
                )

            log.info(
                "[lidar] total tiles across collections: %d (%.1f MB)",
                total,
                total_bytes / 1000000.0,
            )

            return {
                "total_tiles": total,
                "total_bytes": total_bytes,
                "n_collections": len(results),
            }

        layers = select_layers()
        results = fetch_one_layer.expand(layer_meta=layers)
        summary = log_summary(results)

        if cfg.bronze_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze = TriggerDagRunOperator(
                task_id="trigger_lidar_bronze_load",
                trigger_dag_id=cfg.bronze_dag_id,
                wait_for_completion=False,
            )
            summary >> trigger_bronze

    return lidar_aveiro_ingestion()


dag = _create_dag()
