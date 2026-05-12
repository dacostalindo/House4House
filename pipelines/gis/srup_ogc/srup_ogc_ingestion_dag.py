# v2 scope — preserved from .pyc decompile. Day-8 evaluation gate per Sprint-08 plan.
# See wiki/sources/srup-ogc.md for the canonical source spec.

"""
SRUP OGC API Ingestion — omnibus DAG

Iterates over the WS2a registry in srup_ogc_config.py and fetches each layer
from `https://ogcapi.dgterritorio.gov.pt/collections/{id}/items` via the
unified `OgcApiAdapter`. Per-layer outputs land in MinIO under
`raw/srup_ogc/{name}/{YYYYMMDD}/{name}.geojson`.

This is intentionally a SINGLE DAG handling many layers (matching the existing
`srup_ingestion_dag.py` pattern) rather than 12 separate DAGs — keeps the
Airflow UI uncluttered and lets us trigger an "ingest everything" run with one
click.

The actual paginated streaming is delegated to `OgcApiAdapter` from
`pipelines/gis/template/ingestion_template.py` (WS1) — this DAG only adds
the per-layer fan-out + MinIO upload + downstream trigger.

Trigger manually from Airflow UI — no parameters needed.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.srup_ogc.srup_ogc_config import (
    MINIO_BUCKET,
    OGCAPI_BASE,
    SRUP_OGC_CONFIG,
    SRUP_OGC_LAYERS,
    minio_prefix_for,
)

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    cfg = SRUP_OGC_CONFIG

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
        tags=["ingestion", "gis", "minio", "ogc_api"] + cfg.tags,
        params={
            "layer_filter": Param(
                default="",
                description=(
                    "Optional comma-separated list of layer names to ingest "
                    "(e.g. 'srup_zpe,srup_ren_areal'). Empty = ingest all."
                ),
                type="string",
            ),
        },
    )
    def srup_ogc_ingestion():
        @task()
        def select_layers(**context) -> list[dict]:
            """Resolve the param filter against SRUP_OGC_LAYERS."""
            raw = context["params"].get("layer_filter", "").strip()
            if raw:
                wanted = {n.strip() for n in raw.split(",") if n.strip()}
            else:
                wanted = set()

            selected: list[dict] = []
            for layer in SRUP_OGC_LAYERS:
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

            log.info("[srup_ogc] selected layers: %s", [s["name"] for s in selected])

            if not selected:
                raise ValueError(
                    f"No layers matched filter '{raw}'. "
                    f"Available: {[layer.name for layer in SRUP_OGC_LAYERS]}"
                )
            return selected

        @task()
        def fetch_one_layer(layer_meta: dict) -> dict:
            """Fetch one SRUP OGC layer + upload to MinIO."""
            from airflow.models import Variable
            from minio import Minio

            from pipelines.gis.template.ingestion_template import (
                OgcApiAdapter,
                UnifiedIngestionConfig,
            )

            layer_cfg = next(
                (layer for layer in SRUP_OGC_LAYERS if layer.name == layer_meta["name"]),
                None,
            )
            if layer_cfg is None:
                raise ValueError(f"Unknown layer name: {layer_meta['name']}")

            page_size = layer_cfg.page_size_override or cfg.page_size
            request_timeout = layer_cfg.request_timeout_override or cfg.request_timeout_seconds

            adapter_cfg = UnifiedIngestionConfig(
                dag_id=f"_inline_{layer_cfg.name}",
                source_name=layer_cfg.name,
                description=layer_cfg.label,
                protocol="ogc_api",
                endpoint_url=f"{OGCAPI_BASE}/{layer_cfg.collection_id}/items",
                page_size=page_size,
                request_delay_seconds=cfg.request_delay_seconds,
                request_timeout_seconds=request_timeout,
                minio_prefix=minio_prefix_for(layer_cfg),
                bronze_schema_table=layer_cfg.bronze_table,
            )

            log.info(
                "[%s] adapter cfg: collection=%s page_size=%d timeout=%d",
                layer_cfg.name,
                layer_cfg.collection_id,
                page_size,
                request_timeout,
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"srup_ogc_{layer_cfg.name}_")
            try:
                adapter = OgcApiAdapter(adapter_cfg)
                probe = adapter.probe()
                log.info("[%s] probe: %s", layer_cfg.name, probe)

                meta = adapter.fetch_to(tmp_dir)
                log.info(
                    "[%s] fetched %d features in %d pages (%.1f MB)",
                    layer_cfg.name,
                    meta["feature_count"],
                    meta["pages"],
                    meta["bytes"] / 1000000.0,
                )

                if meta["feature_count"] < layer_cfg.expected_min_features:
                    raise ValueError(
                        f"[{layer_cfg.name}] only {meta['feature_count']} features "
                        f"returned, expected >= {layer_cfg.expected_min_features}"
                    )

                endpoint = Variable.get("MINIO_ENDPOINT")
                access_key = Variable.get("MINIO_ACCESS_KEY")
                secret_key = Variable.get("MINIO_SECRET_KEY")
                client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

                if not client.bucket_exists(MINIO_BUCKET):
                    client.make_bucket(MINIO_BUCKET)

                date_str = datetime.utcnow().strftime("%Y%m%d")
                uploaded: list[str] = []
                for local_path in meta["files"]:
                    rel = os.path.relpath(local_path, tmp_dir)
                    object_name = f"{minio_prefix_for(layer_cfg)}/{date_str}/{rel}"
                    client.fput_object(
                        bucket_name=MINIO_BUCKET,
                        object_name=object_name,
                        file_path=local_path,
                    )
                    uploaded.append(object_name)

                return {
                    "name": layer_cfg.name,
                    "collection_id": layer_cfg.collection_id,
                    "feature_count": meta["feature_count"],
                    "pages": meta["pages"],
                    "uploaded": uploaded,
                    "bronze_table": layer_cfg.bronze_table,
                }
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(results: list[dict]) -> dict:
            total = sum(r["feature_count"] for r in results)
            log.info(
                "[srup_ogc] omnibus complete: %d total features across %d layers",
                total,
                len(results),
            )
            return {"total_features": total, "n_layers": len(results)}

        layers = select_layers()
        results = fetch_one_layer.expand(layer_meta=layers)
        summary = log_summary(results)

        if cfg.bronze_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze = TriggerDagRunOperator(
                task_id="trigger_srup_ogc_bronze_load",
                trigger_dag_id=cfg.bronze_dag_id,
                wait_for_completion=False,
            )
            summary >> trigger_bronze

    return srup_ogc_ingestion()


dag = _create_dag()
