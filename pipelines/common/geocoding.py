"""Forward-geocoding via local Nominatim — pure-Python helper.

Reusable across pipelines (currently consumed by sce_geocode_dag). Pattern
mirrors the reverse-geocode helper at idealista_bronze_dag.py:526 (Nominatim
HTTP + rate-limit + per-request try/except), but exposes forward-direction
(`/search`) calls and stays Airflow-free so it can be imported into tests
without DAG context.

Per /plan-eng-review D5 + the Karpathy Rule-3 sprint-08 decision: do NOT
refactor idealista_bronze_dag.py to use this helper (its caller pattern is
reverse-geocode, and refactoring with one current caller is premature).

Caching is the caller's responsibility — this helper does not touch the
warehouse. The caller does its own incremental "doc_number NOT IN cache"
SELECT and persists results.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodeResult:
    """Single Nominatim /search hit.

    `importance` is Nominatim's 0.0-1.0 relevance score and doubles as the
    geocode_confidence value the DAG writes to bronze_enrichment.
    """

    lat: float
    lon: float
    display_name: str
    importance: float
    raw: dict[str, Any]


def nominatim_geocode(
    query: str,
    *,
    url: str = "http://nominatim:8080",
    timeout: int = 10,
    limit: int = 1,
) -> GeocodeResult | None:
    """Single forward-geocode call. Returns None on no-hit / HTTP error.

    Parameters
    ----------
    query :
        Free-text address (e.g. "Rua Direita 199, Aradas, Aveiro, Portugal").
    url :
        Nominatim base URL — defaults to the docker-internal hostname.
    timeout :
        Per-request HTTP timeout (seconds).
    limit :
        Nominatim's `limit` param. Defaults to 1 (we take the top hit).
    """
    if not query or not query.strip():
        return None

    try:
        resp = requests.get(
            f"{url}/search",
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 0},
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:
        # Boundary call: a bad address or transient Nominatim hiccup must not
        # crash the whole batch — yield None and let the caller fall through
        # to the freguesia-centroid tier.
        log.warning("[nominatim] forward-geocode failed for %r: %s", query[:80], exc)
        return None

    if not results:
        return None

    top = results[0]
    try:
        return GeocodeResult(
            lat=float(top["lat"]),
            lon=float(top["lon"]),
            display_name=top.get("display_name", ""),
            importance=float(top.get("importance", 0.0)),
            raw=top,
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("[nominatim] malformed response for %r: %s", query[:80], exc)
        return None


def nominatim_geocode_batch(
    queries: Iterable[tuple[Any, str]],
    *,
    url: str = "http://nominatim:8080",
    rate_limit_seconds: float = 0.02,
    timeout: int = 10,
    progress_every: int = 100,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Iterator[tuple[Any, GeocodeResult | None]]:
    """Rate-limited forward-geocode generator.

    Yields `(key, result)` tuples in input order. `result` is None for
    no-hit / HTTP error rows. Caller handles persistence + retries.

    Parameters
    ----------
    queries :
        Iterable of `(key, query)` pairs. The `key` is opaque (e.g. an SCE
        `doc_number`) and is just passed through to the output — this helper
        does not know what it is.
    url :
        Nominatim base URL.
    rate_limit_seconds :
        Sleep between requests. Defaults to 0.02 (~50 req/s, matching
        idealista's local-Nominatim setting).
    timeout :
        Per-request HTTP timeout (seconds).
    progress_every :
        Log progress every N processed rows. Set to 0 to disable.
    progress_callback :
        Optional `(processed, hits) -> None` callback fired every
        `progress_every` rows.
    """
    queries_list = list(queries)  # materialise so we can report total
    total = len(queries_list)
    processed = 0
    hits = 0

    for key, query in queries_list:
        result = nominatim_geocode(query, url=url, timeout=timeout)
        yield key, result

        processed += 1
        if result is not None:
            hits += 1

        if progress_every and processed % progress_every == 0:
            log.info(
                "[nominatim] progress: %d / %d processed, %d hits",
                processed,
                total,
                hits,
            )
            if progress_callback is not None:
                progress_callback(processed, hits)

        time.sleep(rate_limit_seconds)

    log.info(
        "[nominatim] batch complete: %d processed, %d hits (%.1f%% hit rate)",
        processed,
        hits,
        100.0 * hits / max(processed, 1),
    )
