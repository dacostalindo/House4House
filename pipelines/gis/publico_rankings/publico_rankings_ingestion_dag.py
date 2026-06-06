"""
Público School Rankings — Bronze Ingestion DAG

Fans out over the per-year file resolver table in publico_rankings_config.py
using Airflow dynamic task mapping. Each mapped task downloads one (year, kind)
file, validates against soft-404 + size floor, and uploads to MinIO at
    raw/publico_rankings/{year}/{kind}.json

Why a custom DAG (not the GIS ingestion template):
- The template downloads a single URL; we need to fan out across 12 URLs.
- The template expects GeoPackage/Shapefile/GeoJSON; these are JSON arrays
  served with a .js extension and no geometry library can parse them.
- The Público edge requires a Referer header; the template's downloader
  doesn't accept custom headers.

Trigger:
    Airflow UI → publico_rankings_ingestion → Trigger DAG (no params required;
    full backfill runs every time. Idempotent — re-uploads with same key.)

Refresh cadence: manual; Público releases annually in April. Re-trigger after
adding a new RankingFile row to publico_rankings_config.YEAR_FILE_TABLE.
"""

from __future__ import annotations

import logging
from datetime import timedelta

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.publico_rankings.publico_rankings_config import (
        MINIO_BUCKET,
        MINIO_PREFIX,
        REQUEST_HEADERS,
        SOFT_404_BYTES,
        YEAR_FILE_TABLE,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="publico_rankings_ingestion",
        description=(
            "Download Público annual school rankings (sec + 9ano, 2018-latest) "
            "to MinIO bronze. Per-year URL table in config."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["publico", "rankings", "education", "schools", "p1", "annual"],
    )
    def publico_rankings_ingestion():
        @task()
        def fanout() -> list[dict]:
            """Materialize the year-file table into a list of mappable dicts."""
            return [
                {
                    "year": rf.year,
                    "kind": rf.kind,
                    "url": rf.url,
                    "min_bytes": rf.expected_min_bytes,
                }
                for rf in YEAR_FILE_TABLE
            ]

        @task()
        def download_one(spec: dict) -> dict:
            """Fetch one ranking file, validate size, return bytes payload."""
            import requests

            url = spec["url"]
            min_bytes = spec["min_bytes"]

            log.info("[publico] GET %s", url)
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
            resp.raise_for_status()

            body = resp.content
            n = len(body)

            if n == SOFT_404_BYTES:
                raise ValueError(
                    f"Soft-404 detected for {url}: body is exactly {SOFT_404_BYTES} bytes "
                    "(Publico's HTML 404 page). URL likely moved — update YEAR_FILE_TABLE."
                )
            if n < min_bytes:
                raise ValueError(
                    f"Body too small for {url}: {n} bytes (expected >= {min_bytes}). "
                    "Possible truncation or schema change."
                )

            # Spot-check JSON parses. The .js extension is misleading — file is
            # a plain JSON array. If this trips, Publico has wrapped the payload
            # (e.g. JSONP-style) and the downstream silver parser needs a strip.
            import json

            try:
                json.loads(body)
            except json.JSONDecodeError as e:
                head = body[:120].decode("utf-8", errors="replace")
                raise ValueError(f"Body for {url} is not valid JSON: {e}. Head={head!r}") from e

            return {
                "year": spec["year"],
                "kind": spec["kind"],
                "url": url,
                "size_bytes": n,
                # XCom-friendly: encode the body as latin-1 for transport. Files
                # are < 2 MB so XCom (1 MB default) may need bumping. Alternative:
                # write to a tempfile path and pass the path through XCom instead.
                # Keeping it inline for now; if XCom limits bite, swap to tempdir.
                "body_b64": body.decode("latin-1"),
            }

        @task()
        def upload_one(payload: dict) -> dict:
            """Upload one validated body to MinIO at raw/publico_rankings/{year}/{kind}.json."""
            import io

            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            year = payload["year"]
            kind = payload["kind"]
            object_name = f"{MINIO_PREFIX}/{year}/{kind}.json"
            body = payload["body_b64"].encode("latin-1")

            log.info(
                "[publico] PUT s3://%s/%s (%d bytes)",
                MINIO_BUCKET,
                object_name,
                len(body),
            )
            client.put_object(
                MINIO_BUCKET,
                object_name,
                io.BytesIO(body),
                length=len(body),
                content_type="application/json",
            )
            return {
                "bucket": MINIO_BUCKET,
                "object_name": object_name,
                "year": year,
                "kind": kind,
                "size_bytes": len(body),
            }

        @task()
        def summarize(results: list[dict]) -> dict:
            """Log a one-line per-file summary."""
            for r in results:
                log.info(
                    "[publico] uploaded %s (%d bytes) -> s3://%s/%s",
                    f"{r['year']}/{r['kind']}",
                    r["size_bytes"],
                    r["bucket"],
                    r["object_name"],
                )
            total_bytes = sum(r["size_bytes"] for r in results)
            log.info("[publico] done: %d files, %.1f KB total", len(results), total_bytes / 1024)
            return {"file_count": len(results), "total_bytes": total_bytes}

        specs = fanout()
        downloaded = download_one.expand(spec=specs)
        uploaded = upload_one.expand(payload=downloaded)
        summarize(uploaded)

    return publico_rankings_ingestion()


dag = _create_dag()
