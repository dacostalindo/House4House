"""
SRUP Ingestion — WFS → MinIO

Queries DGTERRITÓRIO's SRUP (Servidões e Restrições de Utilidade Pública) WFS
endpoints for property constraint data and saves GeoJSON to MinIO.

Phase 1: IC (heritage), RAN (agricultural reserve), DPH (public water domain).
All national endpoints, full fetch — no BBOX filtering needed.

Trigger manually from Airflow UI. Supports category filtering via conf:
    {"categories": ["ic", "ran"]}  # IC + RAN only
    {}                              # all configured categories
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import timedelta

from pipelines.gis.srup.srup_config import (
    ALL_CATEGORIES,
    SRUP_CONFIG,
    SRUP_ENDPOINTS_BY_CATEGORY,
    SRUPEndpointConfig,
    normalize_field_name,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_properties(properties: dict) -> dict:
    """Strip diacritics from field names. All fields are passed through."""
    return {normalize_field_name(k): v for k, v in properties.items()}


def _fetch_all_features(
    endpoint: SRUPEndpointConfig,
    feature_type: str,
    timeout: int,
) -> list[dict]:
    """Fetch all GeoJSON features for a feature type in a single WFS request."""
    import requests

    url = endpoint.get_feature_url(feature_type)
    log.info("[srup] Fetching %s from %s", feature_type, endpoint.label)

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    features = data.get("features", [])

    for feature in features:
        feature["properties"] = _normalize_properties(
            feature.get("properties", {})
        )

    log.info(
        "[srup] Got %d features for %s (%.1f MB)",
        len(features),
        feature_type,
        len(resp.content) / 1e6,
    )

    return features


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


def _create_dag():
    from airflow.decorators import dag, task

    cfg = SRUP_CONFIG

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
        max_active_tasks=cfg.max_active_tasks,
        tags=["ingestion", "gis", "minio"] + cfg.tags,
    )
    def srup_ingestion():

        @task()
        def resolve_categories(**context) -> list[str]:
            """Determine which categories to process based on trigger conf."""
            conf = context["dag_run"].conf or {}
            requested = conf.get("categories")

            if requested:
                valid = [c for c in requested if c in ALL_CATEGORIES]
                if not valid:
                    raise ValueError(
                        f"No valid categories in {requested}. "
                        f"Available: {ALL_CATEGORIES}"
                    )
                categories = valid
            else:
                categories = ALL_CATEGORIES

            log.info("[srup] Processing categories: %s", categories)
            return categories

        @task()
        def check_wfs_availability(category: str) -> str:
            """Verify WFS endpoints respond for this category."""
            import requests

            endpoints = SRUP_ENDPOINTS_BY_CATEGORY[category]

            for endpoint in endpoints:
                url = endpoint.get_capabilities_url()
                log.info("[srup] Checking WFS for %s: %s", endpoint.label, url)

                resp = requests.get(url, timeout=cfg.request_timeout_seconds)
                resp.raise_for_status()

                if "WFS_Capabilities" not in resp.text[:2000]:
                    raise RuntimeError(
                        f"WFS for {endpoint.label} returned unexpected content"
                    )
                log.info("[srup] WFS available for %s", endpoint.label)

                time.sleep(cfg.request_delay_seconds)

            return category

        @task()
        def fetch_srup_features(category: str) -> dict:
            """Fetch all features for a category from its WFS endpoints."""
            endpoints = SRUP_ENDPOINTS_BY_CATEGORY[category]
            all_features: list[dict] = []
            feature_type_counts: dict[str, int] = {}

            for endpoint in endpoints:
                for feature_type in endpoint.feature_types:
                    features = _fetch_all_features(
                        endpoint,
                        feature_type,
                        timeout=cfg.request_timeout_seconds,
                    )
                    all_features.extend(features)
                    feature_type_counts[feature_type] = len(features)

                    time.sleep(cfg.request_delay_seconds)

            if not all_features:
                raise RuntimeError(
                    f"No features returned for category {category}"
                )

            # Write combined GeoJSON to temp file
            tmp_dir = tempfile.mkdtemp(prefix=f"srup_{category}_")
            geojson_path = os.path.join(tmp_dir, f"{category}.geojson")

            feature_collection = {
                "type": "FeatureCollection",
                "features": all_features,
            }

            with open(geojson_path, "w", encoding="utf-8") as f:
                json.dump(feature_collection, f, ensure_ascii=False)

            file_size = os.path.getsize(geojson_path)
            log.info(
                "[srup] Wrote %s (%.1f MB, %d features across %d types)",
                geojson_path,
                file_size / 1e6,
                len(all_features),
                len(feature_type_counts),
            )
            for ft, count in feature_type_counts.items():
                log.info("[srup]   %s: %d features", ft, count)

            return {
                "category": category,
                "geojson_path": geojson_path,
                "tmp_dir": tmp_dir,
                "feature_count": len(all_features),
                "file_size_bytes": file_size,
                "feature_type_counts": feature_type_counts,
            }

        @task()
        def save_to_minio(fetch_result: dict) -> dict:
            """Upload GeoJSON to MinIO."""
            from minio import Minio
            from airflow.models import Variable

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

            from datetime import datetime

            date_str = datetime.utcnow().strftime("%Y%m%d")
            category = fetch_result["category"]
            object_name = (
                f"{cfg.minio_prefix}/{category}/{date_str}/{category}.geojson"
            )

            client.fput_object(
                bucket_name=cfg.minio_bucket,
                object_name=object_name,
                file_path=fetch_result["geojson_path"],
            )

            minio_uri = f"s3://{cfg.minio_bucket}/{object_name}"
            log.info("[srup] Uploaded %s → %s", category, minio_uri)

            return {
                "category": category,
                "minio_uri": minio_uri,
                "object_name": object_name,
                "feature_count": fetch_result["feature_count"],
            }

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_results: list[dict], upload_results: list[dict]):
            """Remove temp directories after MinIO uploads complete."""
            for result in fetch_results:
                tmp_dir = result.get("tmp_dir")
                if tmp_dir and os.path.isdir(tmp_dir):
                    shutil.rmtree(tmp_dir)
                    log.info("[srup] Cleaned up %s", tmp_dir)

        @task()
        def log_summary(upload_results: list[dict]):
            """Log ingestion summary."""
            total = sum(r["feature_count"] for r in upload_results)
            log.info(
                "[srup] Ingestion complete: %d features across %d categories",
                total,
                len(upload_results),
            )
            for r in upload_results:
                log.info(
                    "[srup]   %s: %d features → %s",
                    r["category"],
                    r["feature_count"],
                    r["minio_uri"],
                )

        # --- Task wiring ---
        categories = resolve_categories()

        checked = check_wfs_availability.expand(category=categories)
        fetched = fetch_srup_features.expand(category=checked)
        uploaded = save_to_minio.expand(fetch_result=fetched)

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

    return srup_ingestion()


dag = _create_dag()
