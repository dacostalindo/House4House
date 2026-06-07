"""
DGES CNA acesso — single-(year, phase) ingestion DAG.

Looks up the URL for the given (year, phase) in YEAR_PHASE_URLS, downloads
the file (XLSX/XLS/ODS), validates it (size band, parses with the right
engine, row-count band), and uploads as-is to
    raw/dges_acesso/{year}/fase_{n}/{filename_from_url}

Sibling DAGs:
    dges_acesso_backfill        — runs this logic for every (year, phase) in the manifest
    dges_acesso_bronze_load     — loads ALL MinIO blobs into bronze_education.raw_dges_acesso

Trigger:
    Airflow UI → dges_acesso_ingestion → Trigger DAG with conf:
        {"year": 2025, "phase": 1}

Refresh cadence: manual. DGES publishes 1ª fase in late August / 2ª in mid-
September / 3ª in early October each year. Trigger when the historical-data
page shows the new file.
"""

from __future__ import annotations

import base64
import logging
from datetime import timedelta

log = logging.getLogger(__name__)


def _engine_for(url: str) -> str:
    suffix = url.rsplit(".", 1)[-1].lower()
    if suffix == "xlsx":
        return "openpyxl"
    if suffix == "xls":
        return "xlrd"
    if suffix == "ods":
        return "odf"
    raise ValueError(f"Unsupported file extension for URL {url!r}")


def _count_data_rows(body: bytes, engine: str) -> int:
    """Parse the file just enough to count data rows for sanity-band validation.
    Skips title rows + header + the .ods (1)(2)... annotation row by checking
    codigo_instit shape (col index 1 after leading blank col)."""
    import io
    import re

    import pandas as pd

    # header=None to read everything raw; first sheet only.
    df = pd.read_excel(io.BytesIO(body), engine=engine, sheet_name=0, header=None)
    n = 0
    code_pat = re.compile(r"^[0-9A-Za-z]{2,5}$")
    for i in range(len(df)):
        cell = df.iat[i, 1] if df.shape[1] > 1 else None  # column B
        if cell is None:
            continue
        s = str(cell).strip()
        if not s or s == "nan":
            continue
        if not code_pat.fullmatch(s):
            continue
        # Skip the header row which has "Código Instit." in col B
        if "ódigo" in s or "Instit" in s:
            continue
        n += 1
    return n


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.dges_acesso.dges_acesso_config import (
        MAX_DATA_ROWS,
        MAX_FILE_BYTES,
        MIN_DATA_ROWS,
        MIN_FILE_BYTES,
        MINIO_BUCKET,
        REQUEST_HEADERS,
        YEAR_PHASE_URLS,
        filename_for,
        minio_object_name,
        url_for,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="dges_acesso_ingestion",
        description=(
            "DGES CNA acesso — single-(year, phase) XLSX/XLS/ODS ingest. "
            'Trigger with conf: {"year": YYYY, "phase": N}. '
            "12 yrs × 3 phases = 36 files in the manifest."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["dges_acesso", "dges", "education", "higher_ed", "p1"],
    )
    def dges_acesso_ingestion():
        @task()
        def resolve_target(**context) -> dict:
            conf = (context.get("dag_run") and context["dag_run"].conf) or {}
            year = conf.get("year")
            phase = conf.get("phase")
            if year is None or phase is None:
                raise ValueError(
                    f'Trigger with conf {{"year": YYYY, "phase": N}}. Got conf={conf!r}'
                )
            year, phase = int(year), int(phase)
            if (year, phase) not in YEAR_PHASE_URLS:
                raise ValueError(
                    f"(year={year}, phase={phase}) not in manifest. "
                    f"Available years: {sorted({y for y, _ in YEAR_PHASE_URLS})}"
                )
            return {"year": year, "phase": phase, "url": url_for(year, phase)}

        @task()
        def download_and_validate(target: dict) -> dict:
            import requests

            url = target["url"]
            engine = _engine_for(url)
            log.info("[dges_acesso] GET %s (engine=%s)", url, engine)

            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
            resp.raise_for_status()
            body = resp.content
            size = len(body)
            log.info("[dges_acesso] downloaded %d bytes", size)

            if size < MIN_FILE_BYTES or size > MAX_FILE_BYTES:
                raise ValueError(
                    f"File size {size} outside sanity band "
                    f"[{MIN_FILE_BYTES}, {MAX_FILE_BYTES}]. URL drift or truncation."
                )

            n_rows = _count_data_rows(body, engine)
            log.info("[dges_acesso] probe: %d data rows", n_rows)
            if n_rows < MIN_DATA_ROWS or n_rows > MAX_DATA_ROWS:
                raise ValueError(
                    f"Row count {n_rows} outside sanity band "
                    f"[{MIN_DATA_ROWS}, {MAX_DATA_ROWS}]. Schema drift?"
                )

            return {
                "year": target["year"],
                "phase": target["phase"],
                "url": url,
                "engine": engine,
                "size_bytes": size,
                "n_rows": n_rows,
                "filename": filename_for(target["year"], target["phase"]),
                "body_b64": base64.b64encode(body).decode("ascii"),
            }

        @task()
        def upload_to_minio(payload: dict) -> dict:
            import io

            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            object_name = minio_object_name(payload["year"], payload["phase"])
            body = base64.b64decode(payload["body_b64"])

            log.info(
                "[dges_acesso] PUT s3://%s/%s (%d bytes)",
                MINIO_BUCKET,
                object_name,
                len(body),
            )
            client.put_object(
                MINIO_BUCKET,
                object_name,
                io.BytesIO(body),
                length=len(body),
                content_type="application/octet-stream",
            )
            return {
                "bucket": MINIO_BUCKET,
                "object_name": object_name,
                "year": payload["year"],
                "phase": payload["phase"],
                "size_bytes": len(body),
                "n_rows": payload["n_rows"],
            }

        @task()
        def summarize(upload_result: dict) -> dict:
            log.info(
                "[dges_acesso] done: year=%d phase=%d, %d rows, %d bytes, blob=s3://%s/%s",
                upload_result["year"],
                upload_result["phase"],
                upload_result["n_rows"],
                upload_result["size_bytes"],
                upload_result["bucket"],
                upload_result["object_name"],
            )
            return upload_result

        target = resolve_target()
        payload = download_and_validate(target)
        uploaded = upload_to_minio(payload)
        summarize(uploaded)

    return dges_acesso_ingestion()


dag = _create_dag()
