"""
DGEEC Estabelecimentos do Ensino Superior — Bronze Ingestion DAG.

Downloads the shapefile ZIP bundle from DGTerritorio's ATOM mirror, validates
it (size, ZIP integrity, sidecar presence, pyogrio probe of feature count +
CRS + geometry type), and uploads the ZIP as-is to
    raw/dgeec_ens_sup/{run_date}/Estab_Ens_Sup_Portugal.zip

ZIP is stored intact (no extraction) so the bronze loader can re-extract on
its own worker. Shapefiles are bundles of 5+ sidecars — splitting them on
ingest would multiply MinIO writes for no consumer benefit.

Trigger:
    Airflow UI → dgeec_ens_sup_ingestion → Trigger DAG (no params required).

Refresh cadence: manual. DGEEC publishes irregularly (years between releases).
Probe quarterly; trigger when the .dbf mtime advances.
"""

from __future__ import annotations

import base64
import logging
from datetime import timedelta

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.dgeec_ens_sup.dgeec_ens_sup_config import (
        DOWNLOAD_URL,
        EXPECTED_CRS_EPSG,
        EXPECTED_GEOMETRY_TYPE,
        LAYER_NAME,
        MAX_FEATURES,
        MAX_ZIP_BYTES,
        MIN_FEATURES,
        MIN_ZIP_BYTES,
        MINIO_BUCKET,
        MINIO_PREFIX,
        REQUEST_HEADERS,
        REQUIRED_SIDECAR_EXTS,
        ZIP_FILENAME,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="dgeec_ens_sup_ingestion",
        description=(
            "DGEEC Estabelecimentos do Ensino Superior — shapefile ZIP "
            "ingest from DGTerritorio ATOM mirror (321 UOs, point geometry, "
            "EPSG:4326). Stored as ZIP; bronze loader extracts."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["dgeec_ens_sup", "dgeec", "education", "higher_ed", "shapefile", "p1"],
    )
    def dgeec_ens_sup_ingestion():
        @task()
        def download_and_validate(**context) -> dict:
            """Fetch the ZIP, validate it, return base64 body + probe metadata."""
            import io
            import tempfile
            import zipfile
            from pathlib import Path

            import pyogrio
            import requests

            log.info("[dgeec_ens_sup] GET %s", DOWNLOAD_URL)
            resp = requests.get(DOWNLOAD_URL, headers=REQUEST_HEADERS, timeout=60)
            resp.raise_for_status()
            body = resp.content
            size = len(body)
            log.info("[dgeec_ens_sup] downloaded %d bytes", size)

            if size < MIN_ZIP_BYTES or size > MAX_ZIP_BYTES:
                raise ValueError(
                    f"ZIP size {size} outside sanity band "
                    f"[{MIN_ZIP_BYTES}, {MAX_ZIP_BYTES}]. Endpoint drift or "
                    f"truncated download."
                )

            if not zipfile.is_zipfile(io.BytesIO(body)):
                raise ValueError(
                    f"Downloaded {size} bytes is not a valid ZIP archive. Head={body[:64]!r}"
                )

            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                names = zf.namelist()
                exts = {Path(n).suffix.lower() for n in names}
                missing = [e for e in REQUIRED_SIDECAR_EXTS if e not in exts]
                if missing:
                    raise ValueError(
                        f"ZIP missing required shapefile sidecars: {missing}. Contents: {names}"
                    )
                log.info("[dgeec_ens_sup] ZIP contents: %s", names)

                with tempfile.TemporaryDirectory(prefix="dgeec_ens_sup_") as td:
                    zf.extractall(td)
                    shp_path = next(Path(td).glob("*.shp"))
                    info = pyogrio.read_info(str(shp_path))

            n_features = int(info["features"])
            crs = str(info.get("crs"))
            geom_type = str(info.get("geometry_type"))
            log.info(
                "[dgeec_ens_sup] probe: features=%d crs=%s geom=%s layer=%s",
                n_features,
                crs,
                geom_type,
                info.get("layer_name"),
            )

            if n_features < MIN_FEATURES or n_features > MAX_FEATURES:
                raise ValueError(
                    f"Feature count {n_features} outside sanity band "
                    f"[{MIN_FEATURES}, {MAX_FEATURES}]."
                )
            if crs != f"EPSG:{EXPECTED_CRS_EPSG}":
                # Warning only — bronze re-projects from native to 4326+3763
                # via ST_Transform regardless.
                log.warning(
                    "[dgeec_ens_sup] CRS drift: got %r, expected EPSG:%d",
                    crs,
                    EXPECTED_CRS_EPSG,
                )
            if geom_type != EXPECTED_GEOMETRY_TYPE:
                raise ValueError(
                    f"Geometry type {geom_type!r} != expected "
                    f"{EXPECTED_GEOMETRY_TYPE!r}. Schema change at DGEEC."
                )
            if info.get("layer_name") != LAYER_NAME:
                log.warning(
                    "[dgeec_ens_sup] layer name drift: got %r, expected %r",
                    info.get("layer_name"),
                    LAYER_NAME,
                )

            run_date = context["ds"]  # YYYY-MM-DD
            return {
                "run_date": run_date,
                "size_bytes": size,
                "n_features": n_features,
                "crs": crs,
                "geom_type": geom_type,
                "layer_name": info.get("layer_name"),
                "zip_filenames": names,
                "body_b64": base64.b64encode(body).decode("ascii"),
            }

        @task()
        def upload_to_minio(payload: dict) -> dict:
            """Upload the validated ZIP as-is to MinIO."""
            import io

            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            run_date = payload["run_date"]
            object_name = f"{MINIO_PREFIX}/{run_date}/{ZIP_FILENAME}"
            body = base64.b64decode(payload["body_b64"])

            log.info(
                "[dgeec_ens_sup] PUT s3://%s/%s (%d bytes)",
                MINIO_BUCKET,
                object_name,
                len(body),
            )
            client.put_object(
                MINIO_BUCKET,
                object_name,
                io.BytesIO(body),
                length=len(body),
                content_type="application/zip",
            )
            return {
                "bucket": MINIO_BUCKET,
                "object_name": object_name,
                "run_date": run_date,
                "size_bytes": len(body),
                "n_features": payload["n_features"],
            }

        @task()
        def summarize(upload_result: dict) -> dict:
            log.info(
                "[dgeec_ens_sup] done: run_date=%s, %d features, %d bytes, blob=s3://%s/%s",
                upload_result["run_date"],
                upload_result["n_features"],
                upload_result["size_bytes"],
                upload_result["bucket"],
                upload_result["object_name"],
            )
            return upload_result

        payload = download_and_validate()
        uploaded = upload_to_minio(payload)
        summarize(uploaded)

    return dgeec_ens_sup_ingestion()


dag = _create_dag()
