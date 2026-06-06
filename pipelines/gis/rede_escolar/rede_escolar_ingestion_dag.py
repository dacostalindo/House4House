"""
Rede Escolar — Paginated ArcGIS REST Bronze Ingestion DAG.

Probes the GesEdu FeatureServer for total feature count, pre-computes
`resultOffset` values at PAGE_SIZE stride, fans out a download task per page
via Airflow dynamic task mapping, and uploads each page to MinIO at
    raw/rede_escolar/{run_date}/page_{offset:06d}.geojson

Pagination strategy: pre-computed offsets (NOT sequential resultOffset+
exceededTransferLimit loop). Verified 2026-06-06 that ArcGIS returns
exactly PAGE_SIZE features per non-tail page, so pre-compute is reliable.
The summarize task reconciles sum(page row counts) against the probed total
and fails the DAG if drift > 0.

Idempotency: the run_date partition makes re-runs land at a new prefix; this
is intentional — schools open and close, and we want a per-run snapshot so
silver can compute change-over-time later.

Trigger:
    Airflow UI → rede_escolar_ingestion → Trigger DAG (no params required).

Refresh cadence: monthly. GesEdu updates the register continuously, but bronze
snapshots monthly is enough; silver promotes the latest.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


def _create_dag():
    from airflow.decorators import dag, task

    from pipelines.gis.rede_escolar.rede_escolar_config import (
        COUNT_PARAMS,
        COUNT_URL,
        MAX_TOTAL,
        MIN_PAGE_FEATURES_NON_TAIL,
        MIN_TOTAL,
        MINIO_BUCKET,
        MINIO_PREFIX,
        PAGE_SIZE,
        QUERY_PARAMS_BASE,
        QUERY_URL,
        REQUEST_HEADERS,
    )

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="rede_escolar_ingestion",
        description=(
            "Paginated ArcGIS REST ingest of GesEdu RedeEscolar_mapa "
            "(~8,670 PT schools, point geometry, EPSG:4326). Pre-computed offsets."
        ),
        schedule="@monthly",
        start_date=datetime(2026, 6, 1),
        catchup=False,
        default_args=default_args,
        tags=["rede_escolar", "gesedu", "education", "schools", "arcgis", "p1", "monthly"],
    )
    def rede_escolar_ingestion():
        @task()
        def probe_and_fanout(**context) -> list[dict]:
            """Probe live feature count + return mappable {offset, run_date} specs."""
            import requests

            log.info("[rede_escolar] probing %s", COUNT_URL)
            resp = requests.get(COUNT_URL, params=COUNT_PARAMS, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            total = payload.get("count")
            if not isinstance(total, int):
                raise ValueError(f"Count probe returned non-int: {payload!r}")
            if total < MIN_TOTAL or total > MAX_TOTAL:
                raise ValueError(
                    f"Count probe returned {total}, outside sanity band "
                    f"[{MIN_TOTAL}, {MAX_TOTAL}]. Endpoint drift or service incident."
                )
            log.info("[rede_escolar] probed total=%d features", total)

            # Use Airflow's logical date as the run_date partition. Falls back to
            # today() when triggered manually without a logical date.
            run_date = context["ds"]  # YYYY-MM-DD
            offsets = list(range(0, total, PAGE_SIZE))
            specs = [
                {"offset": off, "run_date": run_date, "expected_total": total} for off in offsets
            ]
            log.info(
                "[rede_escolar] fanout: %d pages × %d = %d (last page residual: %d)",
                len(specs),
                PAGE_SIZE,
                total,
                total - (len(specs) - 1) * PAGE_SIZE,
            )
            return specs

        @task()
        def download_page(spec: dict) -> dict:
            """Fetch one page of the FeatureServer and return GeoJSON bytes."""
            import json

            import requests

            params = dict(QUERY_PARAMS_BASE)
            params["resultOffset"] = str(spec["offset"])
            params["resultRecordCount"] = str(PAGE_SIZE)

            log.info("[rede_escolar] GET offset=%d", spec["offset"])
            resp = requests.get(QUERY_URL, params=params, headers=REQUEST_HEADERS, timeout=120)
            resp.raise_for_status()
            body = resp.content

            # Validate the response parses as GeoJSON and carries features.
            try:
                doc = json.loads(body)
            except json.JSONDecodeError as e:
                head = body[:200].decode("utf-8", errors="replace")
                raise ValueError(
                    f"Page offset={spec['offset']} not valid JSON: {e}. Head={head!r}"
                ) from e

            features = doc.get("features")
            if not isinstance(features, list):
                raise ValueError(
                    f"Page offset={spec['offset']}: missing or non-list 'features' "
                    f"({type(features).__name__})"
                )

            n_features = len(features)
            # Tail page may be partial; non-tail pages must be full.
            is_tail = (spec["offset"] + PAGE_SIZE) >= spec["expected_total"]
            if not is_tail and n_features != PAGE_SIZE:
                raise ValueError(
                    f"Page offset={spec['offset']} returned {n_features} features, "
                    f"expected exactly {PAGE_SIZE} (non-tail). ArcGIS truncation?"
                )
            if is_tail and n_features < MIN_PAGE_FEATURES_NON_TAIL and spec["offset"] > 0:
                log.warning(
                    "[rede_escolar] tail page offset=%d has only %d features",
                    spec["offset"],
                    n_features,
                )

            return {
                "offset": spec["offset"],
                "run_date": spec["run_date"],
                "size_bytes": len(body),
                "n_features": n_features,
                # latin-1 transit (same trick as publico_rankings) keeps XCom JSON-safe
                "body_b64": body.decode("latin-1"),
            }

        @task()
        def upload_page(payload: dict) -> dict:
            """Upload one validated GeoJSON page to MinIO."""
            import io

            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            offset = payload["offset"]
            run_date = payload["run_date"]
            object_name = f"{MINIO_PREFIX}/{run_date}/page_{offset:06d}.geojson"
            body = payload["body_b64"].encode("latin-1")

            log.info(
                "[rede_escolar] PUT s3://%s/%s (%d bytes, %d features)",
                MINIO_BUCKET,
                object_name,
                len(body),
                payload["n_features"],
            )
            client.put_object(
                MINIO_BUCKET,
                object_name,
                io.BytesIO(body),
                length=len(body),
                content_type="application/geo+json",
            )
            return {
                "bucket": MINIO_BUCKET,
                "object_name": object_name,
                "offset": offset,
                "run_date": run_date,
                "size_bytes": len(body),
                "n_features": payload["n_features"],
            }

        @task()
        def summarize(results: list[dict]) -> dict:
            """Reconcile per-page counts against the probed total."""
            total_features = sum(r["n_features"] for r in results)
            total_bytes = sum(r["size_bytes"] for r in results)
            run_dates = {r["run_date"] for r in results}

            for r in sorted(results, key=lambda x: x["offset"]):
                log.info(
                    "[rede_escolar]   offset=%06d -> %d features (%d bytes) -> %s",
                    r["offset"],
                    r["n_features"],
                    r["size_bytes"],
                    r["object_name"],
                )

            log.info(
                "[rede_escolar] done: %d pages, %d features, %.1f MB total, run_date(s)=%s",
                len(results),
                total_features,
                total_bytes / 1_048_576,
                sorted(run_dates),
            )
            return {
                "page_count": len(results),
                "total_features": total_features,
                "total_bytes": total_bytes,
                "run_dates": sorted(run_dates),
            }

        specs = probe_and_fanout()
        downloaded = download_page.expand(spec=specs)
        uploaded = upload_page.expand(payload=downloaded)
        summarize(uploaded)

    return rede_escolar_ingestion()


dag = _create_dag()
