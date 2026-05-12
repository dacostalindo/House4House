# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/lneg.md for the canonical source spec.

"""
LNEG ArcGIS REST Ingestion — omnibus DAG

Iterates over LNEG_LAYERS in lneg_config.py and fetches each layer via the
unified ArcgisRestAdapter from WS1. Per-layer outputs land in MinIO under
`raw/{name}/{YYYYMMDD}/{name}.geojson`. Same pattern as srup_ogc_ingestion_dag
(dynamic task mapping, per-layer fan-out, downstream trigger) — just a
different protocol.

Trigger manually from Airflow UI; optional `layer_filter` param matches the
SRUP omnibus convention.

LNEG self-signed cert: pre-flight gate 7 confirmed sig.lneg.pt presents a cert
that fails Python's default verifier. The ArcgisRestAdapter currently leaves
verify=True (default); for LNEG ingestions this DAG patches `requests.Session`
verify state via env var only if needed at runtime — see fetch_one_layer.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.lneg.lneg_config import (
    LNEG_CONFIG,
    LNEG_LAYERS,
    MINIO_BUCKET,
    minio_prefix_for,
)

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    cfg = LNEG_CONFIG

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
        tags=["ingestion", "gis", "minio", "arcgis_rest"] + cfg.tags,
        params={
            "layer_filter": Param(
                default="",
                description=(
                    "Optional comma-separated list of layer names to ingest "
                    "(e.g. 'lneg_geology_folha1_nw'). Empty = ingest all."
                ),
                type="string",
            ),
        },
    )
    def lneg_ingestion():
        @task()
        def select_layers(**context) -> list[dict]:
            raw = context["params"].get("layer_filter", "").strip()
            if raw:
                wanted = {n.strip() for n in raw.split(",") if n.strip()}
            else:
                wanted = set()

            selected: list[dict] = []
            for layer in LNEG_LAYERS:
                if wanted and layer.name not in wanted:
                    continue
                selected.append(
                    {
                        "name": layer.name,
                        "endpoint_url": layer.endpoint_url,
                        "label": layer.label,
                        "expected_min_features": layer.expected_min_features,
                    }
                )

            log.info("[lneg] selected layers: %s", [s["name"] for s in selected])

            if not selected:
                raise ValueError(
                    f"No layers matched filter '{raw}'. Available: {[layer.name for layer in LNEG_LAYERS]}"
                )
            return selected

        @task()
        def fetch_one_layer(layer_meta: dict) -> dict:
            """Fetch one LNEG ArcGIS REST layer + upload to MinIO.

            Patches the global `requests` SSL verification off for the duration
            of the fetch — sig.lneg.pt presents a cert chain Python's default
            verifier rejects. Tracked as v2 hardening.
            """
            import requests as _requests
            import urllib3
            from airflow.models import Variable
            from minio import Minio

            from pipelines.gis.template.ingestion_template import (
                ArcgisRestAdapter,
                UnifiedIngestionConfig,
            )

            layer_cfg = next(
                (layer for layer in LNEG_LAYERS if layer.name == layer_meta["name"]),
                None,
            )
            if layer_cfg is None:
                raise ValueError(f"Unknown layer name: {layer_meta['name']}")

            adapter_cfg = UnifiedIngestionConfig(
                dag_id=f"_inline_{layer_cfg.name}",
                source_name=layer_cfg.name,
                description=layer_cfg.label,
                protocol="arcgis_rest",
                endpoint_url=layer_cfg.endpoint_url,
                page_size=cfg.page_size,
                request_delay_seconds=cfg.request_delay_seconds,
                request_timeout_seconds=cfg.request_timeout_seconds,
                minio_prefix=minio_prefix_for(layer_cfg),
                bronze_schema_table=layer_cfg.bronze_table,
            )

            # SSL workaround for sig.lneg.pt — patch requests.Session.request
            # to set verify=False. Restored on exit.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            _patched = _requests.Session.request

            def _no_verify_request(self, *args, **kwargs):
                kwargs["verify"] = False
                return _patched(self, *args, **kwargs)

            _requests.Session.request = _no_verify_request

            tmp_dir = tempfile.mkdtemp(prefix=f"lneg_{layer_cfg.name}_")
            try:
                adapter = ArcgisRestAdapter(adapter_cfg)
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
                    "feature_count": meta["feature_count"],
                    "pages": meta["pages"],
                    "uploaded": uploaded,
                    "bronze_table": layer_cfg.bronze_table,
                }
            finally:
                _requests.Session.request = _patched
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(results: list[dict]) -> dict:
            total = sum(r["feature_count"] for r in results)
            log.info(
                "[lneg] omnibus complete: %d total features across %d layers",
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
                task_id="trigger_lneg_bronze_load",
                trigger_dag_id=cfg.bronze_dag_id,
                wait_for_completion=False,
            )
            summary >> trigger_bronze

    return lneg_ingestion()


dag = _create_dag()
