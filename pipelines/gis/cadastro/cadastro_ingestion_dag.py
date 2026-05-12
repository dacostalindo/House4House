"""
Cadastro Predial Ingestion — OGC API → MinIO

Paginates through DGTERRITÓRIO's OGC API Features endpoint via the WS1
`OgcApiAdapter` and uploads the combined GeoJSON FeatureCollection to MinIO
at `raw/cadastro/{YYYYMMDD}/cadastro.geojson`.

Trigger manually from Airflow UI — no config parameters needed.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.cadastro.cadastro_config import CADASTRO_CONFIG

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task

    cfg = CADASTRO_CONFIG

    default_args = {
        "owner": "data-engineering",
        "retries": cfg.retries,
        "retry_delay": timedelta(minutes=cfg.retry_delay_minutes),
    }

    @dag(
        dag_id=cfg.dag_id,
        description=cfg.description,
        schedule=cfg.schedule,
        start_date=cfg.start_date,
        catchup=False,
        default_args=default_args,
        max_active_runs=cfg.max_active_runs,
        tags=["ingestion", "gis", "minio", "ogc_api"] + cfg.tags,
    )
    def cadastro_ingestion():
        @task()
        def probe_endpoint() -> dict:
            from pipelines.gis.template.ingestion_template import (
                OgcApiAdapter,
                UnifiedIngestionConfig,
            )

            adapter_cfg = UnifiedIngestionConfig(
                dag_id="_inline_cadastro_probe",
                source_name=cfg.source_name,
                description=cfg.description,
                protocol="ogc_api",
                endpoint_url=cfg.ogcapi_url,
                page_size=cfg.page_size,
                request_timeout_seconds=cfg.request_timeout_seconds,
                minio_prefix=cfg.minio_prefix,
                bronze_schema_table=cfg.bronze_schema_table,
            )
            adapter = OgcApiAdapter(adapter_cfg)
            info = adapter.probe()
            log.info("[cadastro] probe: %s", info)
            return info

        @task()
        def fetch_to_minio(probe: dict) -> dict:
            from airflow.models import Variable
            from minio import Minio

            from pipelines.gis.template.ingestion_template import (
                OgcApiAdapter,
                UnifiedIngestionConfig,
            )

            adapter_cfg = UnifiedIngestionConfig(
                dag_id="_inline_cadastro_fetch",
                source_name=cfg.source_name,
                description=cfg.description,
                protocol="ogc_api",
                endpoint_url=cfg.ogcapi_url,
                page_size=cfg.page_size,
                request_delay_seconds=cfg.request_delay_seconds,
                request_timeout_seconds=cfg.request_timeout_seconds,
                minio_prefix=cfg.minio_prefix,
                bronze_schema_table=cfg.bronze_schema_table,
            )

            tmp_dir = tempfile.mkdtemp(prefix="cadastro_")
            try:
                adapter = OgcApiAdapter(adapter_cfg)
                meta = adapter.fetch_to(tmp_dir)

                if meta["feature_count"] == 0:
                    raise RuntimeError("No features returned from Cadastro OGC API")

                log.info(
                    "[cadastro] fetched %d features in %d pages (%.1f MB)",
                    meta["feature_count"],
                    meta["pages"],
                    meta["bytes"] / 1_000_000.0,
                )

                endpoint = Variable.get("MINIO_ENDPOINT")
                access_key = Variable.get("MINIO_ACCESS_KEY")
                secret_key = Variable.get("MINIO_SECRET_KEY")
                client = Minio(
                    endpoint, access_key=access_key, secret_key=secret_key, secure=False
                )

                if not client.bucket_exists(cfg.minio_bucket):
                    client.make_bucket(cfg.minio_bucket)

                date_str = datetime.utcnow().strftime("%Y%m%d")
                local_path = meta["files"][0]
                object_name = f"{cfg.minio_prefix}/{date_str}/cadastro.geojson"
                client.fput_object(
                    bucket_name=cfg.minio_bucket,
                    object_name=object_name,
                    file_path=local_path,
                )
                size = os.path.getsize(local_path)
                log.info("[cadastro] uploaded %s (%.1f MB)", object_name, size / 1_000_000.0)

                return {
                    "feature_count": meta["feature_count"],
                    "pages": meta["pages"],
                    "minio_object": object_name,
                    "minio_uri": f"s3://{cfg.minio_bucket}/{object_name}",
                    "size_bytes": size,
                }
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(result: dict) -> dict:
            log.info(
                "[cadastro] ingestion complete: %d features → %s",
                result["feature_count"],
                result.get("minio_uri"),
            )
            return result

        probed = probe_endpoint()
        fetched = fetch_to_minio(probed)
        summary = log_summary(fetched)

        if cfg.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze = TriggerDagRunOperator(
                task_id="trigger_bronze_load",
                trigger_dag_id=cfg.trigger_dag_id,
                wait_for_completion=False,
            )
            summary >> trigger_bronze

    return cadastro_ingestion()


dag = _create_dag()
