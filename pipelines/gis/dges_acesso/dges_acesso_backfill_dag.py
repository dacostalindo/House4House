"""
DGES CNA acesso — full backfill DAG.

Iterates every (year, phase) in YEAR_PHASE_URLS (36 entries spanning
2014–2025) and ingests each into MinIO. Idempotent: re-runs overwrite the
same MinIO blobs. Designed as a one-shot bootstrap; rerun if the manifest
gains entries or if MinIO is wiped.

For incremental ingest of a single new (year, phase) — e.g. when DGES
publishes the next phase in October — use the parametrised
`dges_acesso_ingestion` DAG instead.

Uses one task per (year, phase) for clean failure isolation: if 2018 fase 2
breaks, the other 35 still succeed and we get a targeted retry surface.
"""

from __future__ import annotations

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
    import io
    import re

    import pandas as pd

    df = pd.read_excel(io.BytesIO(body), engine=engine, sheet_name=0, header=None)
    n = 0
    code_pat = re.compile(r"^[0-9A-Za-z]{2,5}$")
    for i in range(len(df)):
        cell = df.iat[i, 1] if df.shape[1] > 1 else None
        if cell is None:
            continue
        s = str(cell).strip()
        if not s or s == "nan":
            continue
        if not code_pat.fullmatch(s):
            continue
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
        minio_object_name,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="dges_acesso_backfill",
        description=(
            "DGES CNA acesso — backfill all 36 (year, phase) files (2014–2025) "
            "into MinIO. One task per file for clean failure isolation."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["dges_acesso", "dges", "education", "higher_ed", "backfill", "p1"],
    )
    def dges_acesso_backfill():
        @task()
        def ingest_one(year: int, phase: int, url: str) -> dict:
            import io

            import requests
            from airflow.models import Variable
            from minio import Minio

            engine = _engine_for(url)
            log.info("[dges_acesso-backfill] %d/fase_%d %s (engine=%s)", year, phase, url, engine)

            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
            resp.raise_for_status()
            body = resp.content
            size = len(body)

            if size < MIN_FILE_BYTES or size > MAX_FILE_BYTES:
                raise ValueError(
                    f"{year}/fase_{phase}: size {size} outside [{MIN_FILE_BYTES}, {MAX_FILE_BYTES}]"
                )

            n_rows = _count_data_rows(body, engine)
            if n_rows < MIN_DATA_ROWS or n_rows > MAX_DATA_ROWS:
                raise ValueError(
                    f"{year}/fase_{phase}: {n_rows} rows outside [{MIN_DATA_ROWS}, {MAX_DATA_ROWS}]"
                )

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            object_name = minio_object_name(year, phase)
            client.put_object(
                MINIO_BUCKET,
                object_name,
                io.BytesIO(body),
                length=size,
                content_type="application/octet-stream",
            )
            log.info(
                "[dges_acesso-backfill] %d/fase_%d: %d rows, %d bytes → s3://%s/%s",
                year,
                phase,
                n_rows,
                size,
                MINIO_BUCKET,
                object_name,
            )
            return {
                "year": year,
                "phase": phase,
                "size_bytes": size,
                "n_rows": n_rows,
                "object_name": object_name,
            }

        @task()
        def summarize(results: list[dict]) -> dict:
            total_rows = sum(r["n_rows"] for r in results)
            total_bytes = sum(r["size_bytes"] for r in results)
            log.info(
                "[dges_acesso-backfill] done: %d files, %d total rows, %d total bytes",
                len(results),
                total_rows,
                total_bytes,
            )
            by_year: dict[int, int] = {}
            for r in results:
                by_year[r["year"]] = by_year.get(r["year"], 0) + r["n_rows"]
            for y in sorted(by_year):
                log.info("[dges_acesso-backfill]   %d: %d rows", y, by_year[y])
            return {"n_files": len(results), "total_rows": total_rows, "total_bytes": total_bytes}

        # Statically expand the manifest at parse time: one task per (year, phase),
        # named "ingest_one_2025_1" etc. for legibility in the Airflow UI.
        results = []
        for (year, phase), url in sorted(YEAR_PHASE_URLS.items()):
            results.append(ingest_one.override(task_id=f"ingest_{year}_f{phase}")(year, phase, url))
        summarize(results)

    return dges_acesso_backfill()


dag = _create_dag()
