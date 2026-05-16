"""Shared MinIO upload helper for GIS ingestion DAGs.

Replaces the ~15-line `Minio(endpoint, access_key, ...) + bucket_exists + fput_object`
boilerplate that was duplicated across every adapter caller. Consumed by:

  - pipelines/gis/cadastro/cadastro_ingestion_dag.py     (single GeoJSON)
  - pipelines/gis/apa/apa_ingestion_dag.py               (single GeoJSON)
  - pipelines/gis/crus_ogc/crus_ogc_ingestion_dag.py     (single GeoJSON)
  - pipelines/gis/lneg/lneg_ingestion_dag.py             (multi-file, dyn-mapped)
  - pipelines/gis/srup_ogc/srup_ogc_ingestion_dag.py     (multi-file, dyn-mapped)
  - pipelines/gis/lidar/lidar_ingestion_dag.py           (tiles + manifest)
  - pipelines/gis/lidar/derive_terrain_dag.py            (derived slope COGs)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)


def _today_utc() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def upload_files_to_minio(
    *,
    files: list[str],
    bucket: str,
    prefix: str,
    source_name: str,
    tmp_dir: str | None = None,
    date_str: str | None = None,
    secure: bool = False,
) -> dict:
    """Upload one or more local files to MinIO under `{bucket}/{prefix}/{date_str}/...`.

    Two object-name modes:

      * **basename mode** (`tmp_dir=None`) — for single-file uploads. The object
        name is `{prefix}/{date_str}/{basename(file)}`. Matches the
        cadastro/apa/crus_ogc shape.
      * **rel-path mode** (`tmp_dir=<path>`) — for multi-file uploads that
        preserve a sub-directory structure (e.g. `tiles/<tile_id>.tif`
        alongside `manifest.json`). The object name is
        `{prefix}/{date_str}/{relpath(file, tmp_dir)}`. Matches the
        lneg/srup_ogc/lidar shape.

    Args:
        files: absolute local paths to upload.
        bucket: MinIO bucket name (created if missing).
        prefix: base prefix WITHOUT the date segment (e.g. `"cadastro"`,
            `"srup_ogc/srup_ren_areal"`, `"lidar/MDT-2m"`).
        source_name: short identifier used in log lines for scoping.
        tmp_dir: when set, enables rel-path mode (see above).
        date_str: YYYYMMDD; defaults to today UTC.
        secure: HTTPS for MinIO; the local stack uses HTTP, so default False.

    Returns:
        {
            "uploaded": list[str],   # object_names actually uploaded
            "bytes": int,            # sum of local file sizes
            "bucket": str,
            "date_str": str,
        }

    Raises:
        FileNotFoundError: if any file in `files` does not exist on disk.
        minio.error.S3Error: surface-up MinIO errors.
    """
    from airflow.models import Variable
    from minio import Minio

    if not files:
        raise ValueError(f"[{source_name}] upload_files_to_minio called with no files")

    resolved_date = date_str or _today_utc()

    endpoint = Variable.get("MINIO_ENDPOINT")
    access_key = Variable.get("MINIO_ACCESS_KEY")
    secret_key = Variable.get("MINIO_SECRET_KEY")
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        log.info("[%s] created MinIO bucket %s", source_name, bucket)

    uploaded: list[str] = []
    total_bytes = 0

    for local_path in files:
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"[{source_name}] {local_path}")

        if tmp_dir is not None:
            rel = os.path.relpath(local_path, tmp_dir)
            object_name = f"{prefix}/{resolved_date}/{rel}"
        else:
            object_name = f"{prefix}/{resolved_date}/{os.path.basename(local_path)}"

        client.fput_object(bucket_name=bucket, object_name=object_name, file_path=local_path)
        size = os.path.getsize(local_path)
        uploaded.append(object_name)
        total_bytes += size
        log.info(
            "[%s] uploaded %s (%.2f MB)",
            source_name,
            object_name,
            size / 1_000_000.0,
        )

    log.info(
        "[%s] %d file(s) uploaded to MinIO, total %.2f MB",
        source_name,
        len(uploaded),
        total_bytes / 1_000_000.0,
    )

    return {
        "uploaded": uploaded,
        "bytes": total_bytes,
        "bucket": bucket,
        "date_str": resolved_date,
    }


__all__ = ["upload_files_to_minio"]
