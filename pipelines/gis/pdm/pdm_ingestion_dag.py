"""
PDM Zoning Ingestion — CRUS WFS → MinIO

Queries DGTERRITÓRIO's CRUS (Carta do Regime de Uso do Solo) WFS endpoints
for each configured municipality and saves GeoJSON FeatureCollections to MinIO.

CRUS is the nationally standardized land-use classification extracted from
each municipality's active PDM, published via OGC WFS 2.0.0.

Trigger manually from Airflow UI. Supports municipality filtering via conf:
    {"municipalities": ["0105", "1106"]}  # Aveiro + Lisboa only
    {}                                     # all configured municipalities
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from pipelines.gis.pdm.pdm_config import (
    MUNICIPALITY_BY_CODE,
    PDM_CONFIG,
    CRUSMunicipalityConfig,
    NORMALIZED_FIELDS,
    normalize_field_name,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_properties(properties: dict) -> dict:
    """Strip accents from field names and keep only known fields."""
    out = {}
    for key, value in properties.items():
        normalized_key = normalize_field_name(key)
        if normalized_key in NORMALIZED_FIELDS:
            out[normalized_key] = value
    return out


def _fetch_all_features(
    municipality: CRUSMunicipalityConfig,
    timeout: int,
) -> list[dict]:
    """Fetch all GeoJSON features for a municipality in a single WFS request.

    DGTERRITÓRIO's WFS ignores STARTINDEX, so pagination is not possible.
    All municipalities have <2,000 features (~15 MB max), so a single
    request is fine.
    """
    import requests

    url = municipality.get_feature_url()
    log.info("[pdm] Fetching all features for %s: %s", municipality.name, url)

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    features = data.get("features", [])

    for feature in features:
        feature["properties"] = _normalize_properties(feature.get("properties", {}))

    log.info(
        "[pdm] Got %d features for %s (%.1f MB)",
        len(features),
        municipality.name,
        len(resp.content) / 1e6,
    )

    return features


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


def _create_dag():
    from airflow.decorators import dag, task

    cfg = PDM_CONFIG

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
    def pdm_crus_ingestion():

        @task()
        def resolve_municipalities(**context) -> list[dict]:
            """Determine which municipalities to process based on trigger conf."""
            conf = context["dag_run"].conf or {}

            requested = conf.get("municipalities")
            if requested:
                munis = [
                    MUNICIPALITY_BY_CODE[code]
                    for code in requested
                    if code in MUNICIPALITY_BY_CODE
                ]
                if not munis:
                    raise ValueError(
                        f"No valid municipality codes in {requested}. "
                        f"Available: {list(MUNICIPALITY_BY_CODE.keys())}"
                    )
            else:
                munis = cfg.municipalities

            log.info(
                "[pdm] Processing %d municipalities: %s",
                len(munis),
                [m.name for m in munis],
            )
            return [
                {"code": m.code, "name": m.name, "feature_type": m.feature_type}
                for m in munis
            ]

        @task()
        def check_wfs_availability(municipality: dict) -> dict:
            """Verify the WFS endpoint responds for this municipality."""
            import requests

            muni = MUNICIPALITY_BY_CODE[municipality["code"]]
            url = muni.get_capabilities_url()

            log.info("[pdm] Checking WFS for %s: %s", muni.name, url)
            resp = requests.get(url, timeout=cfg.request_timeout_seconds)
            resp.raise_for_status()

            if "WFS_Capabilities" not in resp.text[:2000]:
                raise RuntimeError(
                    f"WFS for {muni.name} returned unexpected content "
                    f"(no WFS_Capabilities in response)"
                )

            log.info("[pdm] WFS available for %s", muni.name)
            return municipality

        @task()
        def fetch_crus_features(municipality: dict) -> dict:
            """Fetch all CRUS features for a municipality via WFS."""
            muni = MUNICIPALITY_BY_CODE[municipality["code"]]

            features = _fetch_all_features(
                muni,
                timeout=cfg.request_timeout_seconds,
            )

            if not features:
                raise RuntimeError(
                    f"No features returned from CRUS WFS for {muni.name} ({muni.code})"
                )

            log.info(
                "[pdm] Fetched %d total features for %s",
                len(features),
                muni.name,
            )

            # Write to temp file
            tmp_dir = tempfile.mkdtemp(prefix=f"pdm_{muni.name_lower}_")
            geojson_path = os.path.join(tmp_dir, "crus.geojson")

            feature_collection = {
                "type": "FeatureCollection",
                "features": features,
            }

            with open(geojson_path, "w", encoding="utf-8") as f:
                json.dump(feature_collection, f, ensure_ascii=False)

            file_size = os.path.getsize(geojson_path)
            log.info(
                "[pdm] Wrote %s (%.1f MB, %d features)",
                geojson_path,
                file_size / 1e6,
                len(features),
            )

            return {
                "code": muni.code,
                "name": muni.name,
                "name_lower": muni.name_lower,
                "geojson_path": geojson_path,
                "tmp_dir": tmp_dir,
                "feature_count": len(features),
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
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=False,
            )

            if not client.bucket_exists(cfg.minio_bucket):
                client.make_bucket(cfg.minio_bucket)

            date_str = datetime.utcnow().strftime("%Y%m%d")
            object_name = (
                f"{cfg.minio_prefix}/{fetch_result['name_lower']}"
                f"/{date_str}/crus.geojson"
            )

            client.fput_object(
                bucket_name=cfg.minio_bucket,
                object_name=object_name,
                file_path=fetch_result["geojson_path"],
            )

            minio_uri = f"s3://{cfg.minio_bucket}/{object_name}"
            log.info("[pdm] Uploaded %s → %s", fetch_result["name"], minio_uri)

            return {
                "code": fetch_result["code"],
                "name": fetch_result["name"],
                "minio_uri": minio_uri,
                "object_name": object_name,
                "feature_count": fetch_result["feature_count"],
            }

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_results: list[dict], upload_results: list[dict]):
            """Remove temp directories after MinIO uploads complete.

            Accepts upload_results to ensure cleanup only runs after all uploads
            finish (the parameter value is not used).
            """
            for result in fetch_results:
                tmp_dir = result.get("tmp_dir")
                if tmp_dir and os.path.isdir(tmp_dir):
                    shutil.rmtree(tmp_dir)
                    log.info("[pdm] Cleaned up %s", tmp_dir)

        @task()
        def log_summary(upload_results: list[dict]):
            """Log ingestion summary."""
            total = sum(r["feature_count"] for r in upload_results)
            log.info("[pdm] Ingestion complete: %d features across %d municipalities", total, len(upload_results))
            for r in upload_results:
                log.info("[pdm]   %s: %d features → %s", r["name"], r["feature_count"], r["minio_uri"])

        # --- Task wiring ---
        municipalities = resolve_municipalities()

        checked = check_wfs_availability.expand(municipality=municipalities)
        fetched = fetch_crus_features.expand(municipality=checked)
        uploaded = save_to_minio.expand(fetch_result=fetched)

        # cleanup depends on both fetched (has tmp_dir) and uploaded (must wait)
        cleanup_temp(fetched, uploaded)

        log_summary(uploaded)

        if cfg.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_bronze_dag = TriggerDagRunOperator(
                task_id="trigger_bronze_load",
                trigger_dag_id=cfg.trigger_dag_id,
                wait_for_completion=False,
            )
            uploaded >> trigger_bronze_dag

    return pdm_crus_ingestion()


dag = _create_dag()
