"""
Cadastro Predial Ingestion — OGC API → MinIO

Paginates through DGTERRITÓRIO's OGC API Features endpoint to download
all property parcel boundaries, then stores the combined GeoJSON in MinIO.

Unlike PDM/CRUS (per-municipality WFS endpoints), Cadastro uses a single
OGC API endpoint with limit/offset pagination.

Trigger manually from Airflow UI — no config parameters needed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta

from pipelines.gis.cadastro.cadastro_config import CADASTRO_CONFIG

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_all_features_to_file(
    base_url: str,
    page_size: int,
    timeout: int,
    delay: float,
    output_path: str,
) -> int:
    """Paginate OGC API Features and stream directly to a GeoJSON file.

    Writes features incrementally to avoid OOM on large datasets (1.79M features).
    Returns the total feature count.
    """
    import requests

    total = 0
    offset = 0

    with open(output_path, "w", encoding="utf-8") as f:
        f.write('{"type":"FeatureCollection","features":[\n')
        first = True

        while True:
            url = f"{base_url}?limit={page_size}&offset={offset}&f=json"
            log.info("[cadastro] Fetching offset=%d: %s", offset, url)

            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()

            data = resp.json()
            batch = data.get("features", [])

            if not batch:
                log.info("[cadastro] No more features at offset=%d — pagination complete", offset)
                break

            for feat in batch:
                if not first:
                    f.write(",\n")
                json.dump(feat, f, ensure_ascii=False)
                first = False

            total += len(batch)
            log.info(
                "[cadastro] Got %d features (total: %d, offset: %d)",
                len(batch), total, offset,
            )

            if len(batch) < page_size:
                break

            offset += len(batch)
            time.sleep(delay)

        f.write("\n]}")

    return total


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


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
        tags=["ingestion", "gis", "minio"] + cfg.tags,
    )
    def cadastro_ingestion():

        @task()
        def check_api_availability() -> dict:
            """Verify the OGC API endpoint is reachable."""
            import requests

            url = f"{cfg.ogcapi_url}?limit=1&f=json"
            log.info("[cadastro] Checking OGC API availability: %s", url)

            resp = requests.get(url, timeout=cfg.request_timeout_seconds)
            resp.raise_for_status()

            data = resp.json()
            total = data.get("numberMatched", 0)
            log.info("[cadastro] API available. Total features: %d", total)

            return {"total_features": total}

        @task()
        def fetch_cadastro_features(api_check: dict) -> dict:
            """Fetch all cadastro features via OGC API pagination."""
            tmp_dir = tempfile.mkdtemp(prefix="cadastro_")
            geojson_path = os.path.join(tmp_dir, "cadastro.geojson")

            feature_count = _fetch_all_features_to_file(
                base_url=cfg.ogcapi_url,
                page_size=cfg.page_size,
                timeout=cfg.request_timeout_seconds,
                delay=cfg.request_delay_seconds,
                output_path=geojson_path,
            )

            if feature_count == 0:
                shutil.rmtree(tmp_dir)
                raise RuntimeError("No features returned from Cadastro OGC API")

            file_size = os.path.getsize(geojson_path)
            log.info(
                "[cadastro] Wrote %s (%.1f MB, %d features)",
                geojson_path, file_size / 1e6, feature_count,
            )

            return {
                "geojson_path": geojson_path,
                "tmp_dir": tmp_dir,
                "feature_count": feature_count,
                "file_size_bytes": file_size,
            }

        @task()
        def save_to_minio(fetch_result: dict) -> dict:
            """Upload GeoJSON FeatureCollection to MinIO."""
            from minio import Minio
            from airflow.models import Variable

            endpoint = Variable.get("MINIO_ENDPOINT")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

            if not client.bucket_exists(cfg.minio_bucket):
                client.make_bucket(cfg.minio_bucket)

            date_str = datetime.utcnow().strftime("%Y%m%d")
            object_name = f"{cfg.minio_prefix}/{date_str}/cadastro.geojson"

            client.fput_object(
                bucket_name=cfg.minio_bucket,
                object_name=object_name,
                file_path=fetch_result["geojson_path"],
            )

            minio_uri = f"s3://{cfg.minio_bucket}/{object_name}"
            log.info("[cadastro] Uploaded → %s", minio_uri)

            return {
                "minio_uri": minio_uri,
                "object_name": object_name,
                "feature_count": fetch_result["feature_count"],
            }

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_result: dict, upload_result: dict):
            """Remove temp directory after MinIO upload completes."""
            tmp_dir = fetch_result.get("tmp_dir")
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir)
                log.info("[cadastro] Cleaned up %s", tmp_dir)

        @task()
        def log_summary(upload_result: dict):
            """Log ingestion summary."""
            log.info(
                "[cadastro] Ingestion complete: %d features → %s",
                upload_result["feature_count"],
                upload_result["minio_uri"],
            )

        # --- Task wiring ---
        api_check = check_api_availability()
        fetched = fetch_cadastro_features(api_check)
        uploaded = save_to_minio(fetched)

        cleanup_temp(fetched, uploaded)
        log_summary(uploaded)

        if cfg.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze = TriggerDagRunOperator(
                task_id="trigger_bronze_load",
                trigger_dag_id=cfg.trigger_dag_id,
                wait_for_completion=False,
            )
            uploaded >> trigger_bronze

    return cadastro_ingestion()


dag = _create_dag()
