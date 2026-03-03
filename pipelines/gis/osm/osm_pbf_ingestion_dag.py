"""
OSM PBF Download — Portugal PBF for OSRM Routing

Downloads the Portugal PBF extract from Geofabrik and stores it in MinIO.
This file is used by the OSRM build pipeline (osrm_build_dag.py) for
route preprocessing. Separate from the GPKG pipeline which feeds bronze loading.

Source:  https://download.geofabrik.de/europe/portugal-latest.osm.pbf
Format:  PBF (Protocolbuffer Binary Format)
Size:    ~700 MB
Refresh: Quarterly (manual trigger)

Trigger from Airflow UI with: {"version": "2026-Q1"}
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

PBF_URL = "https://download.geofabrik.de/europe/portugal-latest.osm.pbf"
PBF_FILENAME = "portugal-latest.osm.pbf"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "osm-pbf"

# Minimum expected PBF size: 200 MB (reject truncated downloads)
MIN_FILE_SIZE = 200 * 1024 * 1024


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="osm_pbf_ingestion",
        description="Download Portugal PBF from Geofabrik for OSRM routing",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        params={
            "version": {
                "default": "",
                "description": (
                    "Version tag for this PBF download, e.g. '2026-Q1'. "
                    "Used as MinIO path: raw/osm-pbf/{version}/portugal-latest.osm.pbf"
                ),
            },
        },
        tags=["osm", "pbf", "osrm", "routing", "geofabrik", "quarterly"],
    )
    def osm_pbf_ingestion():

        @task()
        def download_pbf(**context) -> dict:
            """Download PBF from Geofabrik to a temp directory."""
            import requests

            version = context["params"].get("version") or datetime.utcnow().strftime("%Y-Q%q")
            # Fix quarter calculation since %q isn't standard
            now = datetime.utcnow()
            if not context["params"].get("version"):
                quarter = (now.month - 1) // 3 + 1
                version = f"{now.year}-Q{quarter}"

            tmp_dir = tempfile.mkdtemp(prefix="osm_pbf_")
            local_path = os.path.join(tmp_dir, PBF_FILENAME)

            log.info("[osm-pbf] Downloading %s", PBF_URL)
            resp = requests.get(PBF_URL, stream=True, timeout=600)
            resp.raise_for_status()

            downloaded = 0
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)

            size_mb = downloaded / (1024 * 1024)
            log.info("[osm-pbf] Downloaded %.1f MB to %s", size_mb, local_path)

            if downloaded < MIN_FILE_SIZE:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise ValueError(
                    f"PBF file too small: {size_mb:.1f} MB "
                    f"(minimum {MIN_FILE_SIZE / 1024 / 1024:.0f} MB)"
                )

            return {
                "local_path": local_path,
                "tmp_dir": tmp_dir,
                "version": version,
                "size_bytes": downloaded,
            }

        @task()
        def upload_to_minio(download_info: dict) -> dict:
            """Upload PBF to MinIO."""
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            version = download_info["version"]
            object_name = f"{MINIO_PREFIX}/{version}/{PBF_FILENAME}"
            local_path = download_info["local_path"]

            log.info("[osm-pbf] Uploading to s3://%s/%s", MINIO_BUCKET, object_name)
            client.fput_object(
                MINIO_BUCKET,
                object_name,
                local_path,
                content_type="application/octet-stream",
            )

            size_mb = download_info["size_bytes"] / (1024 * 1024)
            log.info("[osm-pbf] Uploaded %.1f MB to s3://%s/%s", size_mb, MINIO_BUCKET, object_name)

            return {
                "bucket": MINIO_BUCKET,
                "object_name": object_name,
                "version": version,
                "size_bytes": download_info["size_bytes"],
            }

        @task()
        def cleanup_and_log(download_info: dict, upload_info: dict) -> dict:
            """Remove temp files and log summary."""
            tmp_dir = download_info["tmp_dir"]
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info("[osm-pbf] Cleaned up %s", tmp_dir)

            size_mb = upload_info["size_bytes"] / (1024 * 1024)
            log.info(
                "[osm-pbf] Done: version=%s, s3://%s/%s (%.1f MB)",
                upload_info["version"],
                upload_info["bucket"],
                upload_info["object_name"],
                size_mb,
            )
            return upload_info

        # --- Task wiring ---
        dl = download_pbf()
        ul = upload_to_minio(dl)
        cleanup_and_log(dl, ul)

    return osm_pbf_ingestion()


dag = _create_dag()
