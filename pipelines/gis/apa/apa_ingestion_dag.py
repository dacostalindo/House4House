# v2 scope — preserved from .pyc decompile, not wired into v1 wedge DAGs.
# See wiki/sources/apa.md for the canonical source spec.

"""
APA ARPSI Floodplain Ingestion DAG

Single-collection ingestion using `ArcgisRestAdapter` from the WS1 unified
template. Fetches 188 features from Aqualogus AGOL FeatureServer to MinIO at
`raw/apa_arpsi/{YYYYMMDD}/apa_arpsi.geojson`.

Trigger manually from Airflow UI — no parameters needed.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.apa.apa_config import APA_CONFIG

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task

    cfg = APA_CONFIG

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
        tags=["ingestion", "gis", "minio", "arcgis_rest"] + cfg.tags,
    )
    def apa_arpsi_ingestion():
        @task()
        def probe_endpoint() -> dict:
            from pipelines.gis.template.ingestion_template import (
                ArcgisRestAdapter,
                UnifiedIngestionConfig,
            )

            adapter_cfg = UnifiedIngestionConfig(
                dag_id="_inline_apa_probe",
                source_name="apa_arpsi",
                description=cfg.description_ingestion,
                protocol="arcgis_rest",
                endpoint_url=cfg.arpsi_url,
                page_size=cfg.page_size,
                request_timeout_seconds=cfg.request_timeout_seconds,
                minio_prefix=cfg.minio_prefix,
                bronze_schema_table=cfg.bronze_schema_table,
            )
            adapter = ArcgisRestAdapter(adapter_cfg)
            info = adapter.probe()
            log.info("[apa_arpsi] probe: %s", info)
            return info

        @task()
        def fetch_to_minio(probe: dict) -> dict:
            from airflow.models import Variable
            from minio import Minio

            from pipelines.gis.template.ingestion_template import (
                ArcgisRestAdapter,
                UnifiedIngestionConfig,
            )

            adapter_cfg = UnifiedIngestionConfig(
                dag_id="_inline_apa_fetch",
                source_name="apa_arpsi",
                description=cfg.description_ingestion,
                protocol="arcgis_rest",
                endpoint_url=cfg.arpsi_url,
                page_size=cfg.page_size,
                request_delay_seconds=cfg.request_delay_seconds,
                request_timeout_seconds=cfg.request_timeout_seconds,
                minio_prefix=cfg.minio_prefix,
                bronze_schema_table=cfg.bronze_schema_table,
            )

            tmp_dir = tempfile.mkdtemp(prefix="apa_arpsi_")
            try:
                adapter = ArcgisRestAdapter(adapter_cfg)
                meta = adapter.fetch_to(tmp_dir)

                log.info(
                    "[apa_arpsi] fetched %d features in %d pages (%.1f MB)",
                    meta["feature_count"],
                    meta["pages"],
                    meta["bytes"] / 1000000.0,
                )

                endpoint = Variable.get("MINIO_ENDPOINT")
                access_key = Variable.get("MINIO_ACCESS_KEY")
                secret_key = Variable.get("MINIO_SECRET_KEY")
                client = Minio(
                    endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=False,
                )

                if not client.bucket_exists(cfg.minio_bucket):
                    client.make_bucket(cfg.minio_bucket)

                date_str = datetime.utcnow().strftime("%Y%m%d")
                local_path = meta["files"][0]
                object_name = f"{cfg.minio_prefix}/{date_str}/apa_arpsi.geojson"
                client.fput_object(
                    bucket_name=cfg.minio_bucket,
                    object_name=object_name,
                    file_path=local_path,
                )
                size = os.path.getsize(local_path)
                log.info(
                    "[apa_arpsi] uploaded %s (%.1f MB)",
                    object_name,
                    size / 1000000.0,
                )

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
                "[apa_arpsi] ingestion complete: %d features → %s",
                result["feature_count"],
                result.get("minio_uri"),
            )
            return result

        probed = probe_endpoint()
        fetched = fetch_to_minio(probed)
        summary = log_summary(fetched)

        if cfg.bronze_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze = TriggerDagRunOperator(
                task_id="trigger_apa_arpsi_bronze_load",
                trigger_dag_id=cfg.bronze_dag_id,
                wait_for_completion=False,
            )
            summary >> trigger_bronze

    return apa_arpsi_ingestion()


dag = _create_dag()
