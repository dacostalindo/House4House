"""Unified GIS ingestion template — three protocol adapters.

Consumed by:
  - pipelines/gis/crus_ogc/ + srup_ogc/ + cadastro/  via OgcApiAdapter
  - pipelines/gis/apa/ + lneg/                       via ArcgisRestAdapter
  - pipelines/gis/lidar/                             via DgtStacAdapter

All three adapters share `UnifiedIngestionConfig` and expose the same
`.probe()` + `.fetch_to(tmp_dir)` interface so consuming DAGs are
protocol-agnostic past the adapter boundary.

`.fetch_to(tmp_dir)` returns a uniform meta dict:
    {feature_count: int, pages: int, bytes: int, files: list[str]}

For OGC API + ArcGIS REST: `files` is `[{tmp_dir}/{source_name}.geojson]` and
`feature_count` is the number of features written. For DGT STAC: `files`
includes one `tiles/{tile_id}.tif` per tile plus a `manifest.json` summary
that downstream `lidar_bronze_dag.py` reads to populate the bronze manifest
table; `feature_count` is the number of tiles.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class UnifiedIngestionConfig(BaseModel):
    """Shared adapter config across the three GIS-source protocols.

    Field meanings depend on `protocol`:

    `protocol="ogc_api"` — `endpoint_url` is the OGC API Features items URL
        (e.g. `https://ogcapi.dgterritorio.gov.pt/collections/crus/items`).
        `collection_id` is unused (the collection lives in the URL).

    `protocol="arcgis_rest"` — `endpoint_url` is the FeatureServer/MapServer
        layer URL ending in `/<layer_id>` (the adapter appends `/query` for
        feature reads and uses the bare URL for count probes).

    `protocol="dgt_stac"` — `endpoint_url` is the STAC root (e.g.
        `https://cdd.dgterritorio.gov.pt/dgt-be`). `collection_id` is the
        STAC collection name (e.g. `"MDT-2m"`) and is sent in the `/v1/search`
        body. `bbox_4326` filters the search to a region. `auth_cookie_variable`
        is the Airflow Variable name holding a Keycloak session cookie.
    """

    dag_id: str
    source_name: str
    description: str
    protocol: str
    endpoint_url: str
    collection_id: str | None = None
    page_size: int = 1000
    request_delay_seconds: float = 0.5
    request_timeout_seconds: int = 120
    bbox_4326: tuple[float, float, float, float] | None = None
    auth_cookie_variable: str | None = None
    minio_prefix: str
    bronze_schema_table: str

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# OGC API Features
# ---------------------------------------------------------------------------


class OgcApiAdapter:
    """OGC API Features — limit/offset pagination → single GeoJSON file."""

    def __init__(self, cfg: UnifiedIngestionConfig):
        if cfg.protocol != "ogc_api":
            raise ValueError(
                f"OgcApiAdapter requires protocol='ogc_api', got '{cfg.protocol}'"
            )
        self.cfg = cfg

    def probe(self) -> dict:
        """GET ?limit=1&f=json. Returns dict with `numberMatched` (when present)."""
        import requests

        url = f"{self.cfg.endpoint_url}?limit=1&f=json"
        resp = requests.get(url, timeout=self.cfg.request_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        info = {
            "endpoint_url": self.cfg.endpoint_url,
            "numberMatched": data.get("numberMatched"),
            "numberReturned": data.get("numberReturned"),
        }
        log.info("[%s] ogc_api probe: %s", self.cfg.source_name, info)
        return info

    def fetch_to(self, tmp_dir: str) -> dict:
        """Stream paginated features to `{tmp_dir}/{source_name}.geojson`.

        If `cfg.bbox_4326` is set, the OGC API `bbox` query parameter is
        appended (lon_min,lat_min,lon_max,lat_max in EPSG:4326). The OGC
        collection's native CRS is assumed to be 4326; if different, the
        `bbox-crs` parameter would also need to be set (not implemented yet —
        no current caller needs it).
        """
        import requests

        output_path = os.path.join(tmp_dir, f"{self.cfg.source_name}.geojson")
        total = 0
        pages = 0
        offset = 0

        bbox_clause = ""
        if self.cfg.bbox_4326 is not None:
            bbox_clause = f"&bbox={','.join(str(c) for c in self.cfg.bbox_4326)}"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","features":[\n')
            first = True

            while True:
                url = (
                    f"{self.cfg.endpoint_url}"
                    f"?limit={self.cfg.page_size}&offset={offset}&f=json"
                    f"{bbox_clause}"
                )
                log.info(
                    "[%s] ogc_api page %d offset=%d%s",
                    self.cfg.source_name,
                    pages,
                    offset,
                    " (bbox-filtered)" if bbox_clause else "",
                )

                resp = requests.get(url, timeout=self.cfg.request_timeout_seconds)
                resp.raise_for_status()
                batch = resp.json().get("features", [])

                if not batch:
                    break

                for feat in batch:
                    if not first:
                        f.write(",\n")
                    json.dump(feat, f, ensure_ascii=False)
                    first = False

                total += len(batch)
                pages += 1

                if len(batch) < self.cfg.page_size:
                    break

                offset += len(batch)
                if self.cfg.request_delay_seconds:
                    time.sleep(self.cfg.request_delay_seconds)

            f.write("\n]}")

        bytes_ = os.path.getsize(output_path)
        log.info(
            "[%s] ogc_api fetch_to wrote %d features in %d pages (%.1f MB)",
            self.cfg.source_name,
            total,
            pages,
            bytes_ / 1_000_000.0,
        )
        return {
            "feature_count": total,
            "pages": pages,
            "bytes": bytes_,
            "files": [output_path],
        }


# ---------------------------------------------------------------------------
# ArcGIS REST FeatureServer/MapServer
# ---------------------------------------------------------------------------


class ArcgisRestAdapter:
    """ArcGIS REST — server-side reproject via outSR=3763 + offset pagination.

    Writes one merged GeoJSON FeatureCollection per layer. The LNEG SSL
    workaround for sig.lneg.pt lives in `lneg_ingestion_dag.py` (it patches
    `requests.Session.request` around the fetch); the adapter stays clean.
    """

    def __init__(self, cfg: UnifiedIngestionConfig):
        if cfg.protocol != "arcgis_rest":
            raise ValueError(
                f"ArcgisRestAdapter requires protocol='arcgis_rest', got '{cfg.protocol}'"
            )
        self.cfg = cfg

    def probe(self) -> dict:
        """GET {layer}/query?where=1=1&returnCountOnly=true&f=json → {count}."""
        import requests

        url = (
            f"{self.cfg.endpoint_url}/query"
            f"?where=1%3D1&returnCountOnly=true&f=json"
        )
        resp = requests.get(url, timeout=self.cfg.request_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        info = {
            "endpoint_url": self.cfg.endpoint_url,
            "count": data.get("count"),
        }
        log.info("[%s] arcgis_rest probe: %s", self.cfg.source_name, info)
        return info

    def fetch_to(self, tmp_dir: str) -> dict:
        """Page through resultOffset/resultRecordCount → merged GeoJSON."""
        import requests

        output_path = os.path.join(tmp_dir, f"{self.cfg.source_name}.geojson")
        total = 0
        pages = 0
        offset = 0

        with open(output_path, "w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","features":[\n')
            first = True

            while True:
                url = (
                    f"{self.cfg.endpoint_url}/query"
                    f"?where=1%3D1"
                    f"&resultOffset={offset}"
                    f"&resultRecordCount={self.cfg.page_size}"
                    f"&outFields=*"
                    f"&outSR=3763"
                    f"&f=geojson"
                )
                log.info(
                    "[%s] arcgis_rest page %d offset=%d",
                    self.cfg.source_name,
                    pages,
                    offset,
                )

                resp = requests.get(url, timeout=self.cfg.request_timeout_seconds)
                resp.raise_for_status()
                batch = resp.json().get("features", [])

                if not batch:
                    break

                for feat in batch:
                    if not first:
                        f.write(",\n")
                    json.dump(feat, f, ensure_ascii=False)
                    first = False

                total += len(batch)
                pages += 1

                if len(batch) < self.cfg.page_size:
                    break

                offset += len(batch)
                if self.cfg.request_delay_seconds:
                    time.sleep(self.cfg.request_delay_seconds)

            f.write("\n]}")

        bytes_ = os.path.getsize(output_path)
        log.info(
            "[%s] arcgis_rest fetch_to wrote %d features in %d pages (%.1f MB)",
            self.cfg.source_name,
            total,
            pages,
            bytes_ / 1_000_000.0,
        )
        return {
            "feature_count": total,
            "pages": pages,
            "bytes": bytes_,
            "files": [output_path],
        }


# ---------------------------------------------------------------------------
# DGT STAC — Keycloak cookie auth + tokenized 302→MinIO presigned downloads
# ---------------------------------------------------------------------------


class DgtStacAdapter:
    """DGT CDD STAC — POST /v1/search + cookie-gated tile downloads.

    Auth flow (per wiki/sources/lidar.md):
      1. POST `{endpoint_url}/v1/search` with bbox + collections filter.
         Catalog access is PUBLIC; no cookie needed for search.
      2. Per item, GET the tokenized asset href with the Keycloak session
         cookie from Airflow Variable `auth_cookie_variable`. Server
         302-redirects to a fresh MinIO presigned URL; `requests` follows
         transparently.

    `fetch_to(tmp_dir)` writes:
      - `{tmp_dir}/tiles/{tile_id}.tif` per tile (the raw asset bytes)
      - `{tmp_dir}/manifest.json` — `{items: [{tile_id, geometry, datetime,
         version, file_size_bytes, pixel_type, nodata_value}, ...]}` for the
         downstream `lidar_bronze_dag.py` to insert into the bronze manifest
         table.
    """

    def __init__(self, cfg: UnifiedIngestionConfig):
        if cfg.protocol != "dgt_stac":
            raise ValueError(
                f"DgtStacAdapter requires protocol='dgt_stac', got '{cfg.protocol}'"
            )
        if not cfg.collection_id:
            raise ValueError("DgtStacAdapter requires collection_id (STAC collection)")
        self.cfg = cfg

    def _search_url(self) -> str:
        return f"{self.cfg.endpoint_url.rstrip('/')}/v1/search"

    def _build_search_body(self, limit: int, token: str | None = None) -> dict:
        body: dict[str, Any] = {
            "collections": [self.cfg.collection_id],
            "limit": limit,
        }
        if self.cfg.bbox_4326 is not None:
            body["bbox"] = list(self.cfg.bbox_4326)
        if token:
            body["token"] = token
        return body

    def probe(self) -> dict:
        """POST /v1/search with limit=1 — return `{numberMatched}` from feature collection."""
        import requests

        resp = requests.post(
            self._search_url(),
            json=self._build_search_body(limit=1),
            timeout=self.cfg.request_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        info = {
            "collection_id": self.cfg.collection_id,
            "numberMatched": data.get("numberMatched"),
            "numberReturned": data.get("numberReturned"),
        }
        log.info("[%s] dgt_stac probe: %s", self.cfg.source_name, info)
        return info

    def _get_cookie(self) -> str:
        from airflow.models import Variable

        if not self.cfg.auth_cookie_variable:
            raise ValueError(
                f"[{self.cfg.source_name}] dgt_stac fetch requires auth_cookie_variable"
            )
        return Variable.get(self.cfg.auth_cookie_variable)

    def fetch_to(self, tmp_dir: str) -> dict:
        """STAC search → per-tile cookie-gated download → tiles/ + manifest.json."""
        import requests

        tiles_dir = os.path.join(tmp_dir, "tiles")
        os.makedirs(tiles_dir, exist_ok=True)

        cookie = self._get_cookie()
        session = requests.Session()
        session.headers.update({"Cookie": cookie})

        items_meta: list[dict] = []
        total_bytes = 0
        pages = 0
        next_token: str | None = None

        # Phase 1 — paginate STAC search, gather item metadata + asset hrefs.
        all_items: list[dict] = []
        while True:
            resp = requests.post(
                self._search_url(),
                json=self._build_search_body(limit=self.cfg.page_size, token=next_token),
                timeout=self.cfg.request_timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", []) or []
            pages += 1
            log.info(
                "[%s] dgt_stac page %d: %d items (cum %d)",
                self.cfg.source_name,
                pages,
                len(features),
                len(all_items) + len(features),
            )

            if not features:
                break
            all_items.extend(features)

            next_token = None
            for link in data.get("links", []) or []:
                if link.get("rel") == "next":
                    body = link.get("body") or {}
                    next_token = body.get("token")
                    break
            if not next_token:
                break
            if self.cfg.request_delay_seconds:
                time.sleep(self.cfg.request_delay_seconds)

        # Phase 2 — for each item, download its primary asset (cookie-gated).
        for it in all_items:
            tile_id = it.get("id") or it.get("properties", {}).get("tile_id")
            if not tile_id:
                log.warning("[%s] skipping item without id", self.cfg.source_name)
                continue
            geometry = it.get("geometry")
            properties = it.get("properties", {}) or {}

            asset_href = self._pick_asset_href(it.get("assets") or {})
            if not asset_href:
                log.warning("[%s] no downloadable asset for tile %s", self.cfg.source_name, tile_id)
                continue

            local_tile = os.path.join(tiles_dir, f"{tile_id}.tif")
            tile_bytes = self._download_tile(session, asset_href, local_tile)
            total_bytes += tile_bytes

            items_meta.append(
                {
                    "tile_id": tile_id,
                    "geometry": geometry,
                    "datetime": properties.get("datetime"),
                    "version": properties.get("version"),
                    "file_size_bytes": tile_bytes,
                    "pixel_type": properties.get("pixel_type", ""),
                    "nodata_value": properties.get("nodata_value"),
                }
            )

            if self.cfg.request_delay_seconds:
                time.sleep(self.cfg.request_delay_seconds)

        # Phase 3 — write the manifest the bronze DAG consumes.
        manifest_path = os.path.join(tmp_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "collection_id": self.cfg.collection_id,
                    "source_endpoint": self.cfg.endpoint_url,
                    "item_count": len(items_meta),
                    "items": items_meta,
                },
                f,
                ensure_ascii=False,
            )

        files = [manifest_path] + [
            os.path.join(tiles_dir, f"{it['tile_id']}.tif") for it in items_meta
        ]

        log.info(
            "[%s] dgt_stac fetch_to: %d tiles, %d STAC pages, %.1f MB",
            self.cfg.source_name,
            len(items_meta),
            pages,
            total_bytes / 1_000_000.0,
        )
        return {
            "feature_count": len(items_meta),
            "pages": pages,
            "bytes": total_bytes,
            "files": files,
        }

    @staticmethod
    def _pick_asset_href(assets: dict) -> str | None:
        """Pick the GeoTIFF asset href. DGT publishes a single 'data' asset per tile."""
        if not assets:
            return None
        preferred = assets.get("data") or assets.get("visual") or assets.get("image")
        if preferred and preferred.get("href"):
            return preferred["href"]
        for asset in assets.values():
            href = asset.get("href")
            if href and (href.endswith(".tif") or href.endswith(".tiff")):
                return href
        return None

    def _download_tile(self, session: Any, href: str, local_path: str) -> int:
        """Stream the tokenized asset URL to local_path; follow 302 transparently."""
        with session.get(
            href,
            stream=True,
            timeout=self.cfg.request_timeout_seconds,
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return os.path.getsize(local_path)


__all__ = [
    "ArcgisRestAdapter",
    "DgtStacAdapter",
    "OgcApiAdapter",
    "UnifiedIngestionConfig",
]
