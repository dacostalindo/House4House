"""
OSRM Build — Extract & Contract for Car, Walking, Cycling

Preprocesses a Portugal PBF file into OSRM routing data using
Contraction Hierarchies (CH). Runs osrm-extract and osrm-contract
via one-off `docker run` containers sharing the osrm_data volume.

Prerequisites:
  1. PBF downloaded to MinIO via osm_pbf_ingestion DAG
  2. Docker socket mounted in Airflow containers

Trigger manually from Airflow UI — no schedule, no config needed.
Loads the latest PBF from MinIO automatically.

After build completes, restart OSRM routing services:
  docker compose restart osrm-car osrm-walking osrm-cycling
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta

log = logging.getLogger(__name__)

MINIO_BUCKET = "raw"
MINIO_PREFIX = "osm-pbf"
PBF_FILENAME = "portugal-latest.osm.pbf"
OSRM_IMAGE = "osrm/osrm-backend:latest"

# OSRM profile configs: (profile_lua, data_subdir)
PROFILES = [
    ("car.lua", "car"),
    ("foot.lua", "walking"),
    ("bicycle.lua", "cycling"),
]

# Shared volume name (matches docker-compose.yml)
OSRM_VOLUME = "house4house_osrm_data"

# Path inside containers where the volume mounts
DATA_DIR = "/data"


def _docker_run(cmd: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    """Run an OSRM command in a one-off container with the shared data volume."""
    # No --name to avoid conflicts on retries
    full_cmd = (
        f"docker run --rm "
        f"-v {OSRM_VOLUME}:{DATA_DIR} "
        f"{OSRM_IMAGE} "
        f"{cmd}"
    )
    log.info("[osrm] Running: %s", full_cmd)
    result = subprocess.run(
        full_cmd, shell=True, check=True,
        capture_output=True, text=True, timeout=timeout,
    )
    if result.stdout:
        log.info("[osrm] stdout (last 500): %s", result.stdout[-500:])
    if result.stderr:
        log.info("[osrm] stderr (last 500): %s", result.stderr[-500:])
    return result


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    }

    @dag(
        dag_id="osrm_build",
        description="Preprocess Portugal PBF into OSRM routing data (car, walking, cycling)",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["osrm", "routing", "osm", "preprocessing"],
    )
    def osrm_build():

        @task()
        def fetch_pbf_to_volume() -> str:
            """Find the latest PBF in MinIO and place it on the OSRM data volume."""
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            # Find the latest PBF version
            objects = list(client.list_objects(MINIO_BUCKET, prefix=f"{MINIO_PREFIX}/", recursive=True))
            pbf_objects = [o for o in objects if o.object_name.endswith(".osm.pbf")]
            if not pbf_objects:
                raise FileNotFoundError(
                    f"No PBF files found in s3://{MINIO_BUCKET}/{MINIO_PREFIX}/"
                )
            latest = sorted(pbf_objects, key=lambda o: o.object_name)[-1]
            log.info("[osrm] Latest PBF: %s (%.1f MB)", latest.object_name, latest.size / (1024 * 1024))

            # Download to temp dir
            tmp_dir = tempfile.mkdtemp(prefix="osrm_pbf_")
            tmp_pbf = os.path.join(tmp_dir, PBF_FILENAME)

            log.info("[osrm] Downloading PBF to temp: %s", tmp_pbf)
            client.fget_object(MINIO_BUCKET, latest.object_name, tmp_pbf)

            size_mb = os.path.getsize(tmp_pbf) / (1024 * 1024)
            log.info("[osrm] Downloaded %.1f MB", size_mb)

            # Create profile subdirectories and copy PBF using a one-off container
            for _, data_subdir in PROFILES:
                _docker_run(
                    f"sh -c 'mkdir -p {DATA_DIR}/{data_subdir}'",
                    timeout=30,
                )

            # Copy PBF into the volume via a temporary container
            # First copy to a helper container, then cp between containers
            # Simpler: use docker cp with a dummy container
            helper_cmd = (
                f"docker create --name osrm-copy-helper "
                f"-v {OSRM_VOLUME}:{DATA_DIR} "
                f"{OSRM_IMAGE} /bin/true"
            )
            subprocess.run(helper_cmd, shell=True, check=True, timeout=30)

            try:
                for _, data_subdir in PROFILES:
                    dest = f"osrm-copy-helper:{DATA_DIR}/{data_subdir}/{PBF_FILENAME}"
                    log.info("[osrm] Copying PBF to %s", dest)
                    subprocess.run(
                        f"docker cp {tmp_pbf} {dest}",
                        shell=True, check=True, timeout=300,
                    )
            finally:
                subprocess.run("docker rm osrm-copy-helper", shell=True, timeout=30)

            # Cleanup temp
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info("[osrm] PBF placed in volume for all 3 profiles")
            return "ready"

        @task()
        def extract_profile(ready: str, profile_lua: str, data_subdir: str) -> dict:
            """Run osrm-extract for a single profile."""
            pbf_path = f"{DATA_DIR}/{data_subdir}/{PBF_FILENAME}"
            osrm_file = pbf_path.replace(".osm.pbf", ".osrm")
            profile_path = f"/opt/{profile_lua}"

            _docker_run(
                f"osrm-extract -p {profile_path} {pbf_path}",
                timeout=3600,
            )

            return {
                "profile_lua": profile_lua,
                "profile": data_subdir,
                "osrm_file": osrm_file,
            }

        @task()
        def contract_profile(extract_info: dict) -> dict:
            """Run osrm-contract for a single profile."""
            data_subdir = extract_info["profile"]
            osrm_file = extract_info["osrm_file"]

            _docker_run(
                f"osrm-contract {osrm_file}",
                timeout=3600,
            )

            return {
                "profile": data_subdir,
                "osrm_file": osrm_file,
                "status": "ready",
            }

        @task()
        def log_summary(results: list[dict]) -> dict:
            """Log build summary."""
            for r in results:
                log.info("[osrm] %s: %s → %s", r["profile"], r["status"], r["osrm_file"])
            log.info(
                "[osrm] Build complete. Restart OSRM containers to pick up new data: "
                "docker compose restart osrm-car osrm-walking osrm-cycling"
            )
            return {"profiles_built": [r["profile"] for r in results]}

        # --- Task wiring ---
        ready = fetch_pbf_to_volume()

        # Extract all 3 profiles
        extracts = []
        for profile_lua, data_subdir in PROFILES:
            ext = extract_profile(ready, profile_lua, data_subdir)
            extracts.append(ext)

        # Contract each profile after extraction
        contracts = []
        for ext in extracts:
            con = contract_profile(ext)
            contracts.append(con)

        # Summarize
        log_summary(contracts)

    return osrm_build()


dag = _create_dag()
