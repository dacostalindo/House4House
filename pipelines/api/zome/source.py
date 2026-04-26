"""dlt source for Zome PT bronze ingestion (SCD2 + per-entity heartbeat sidecars).

Tables produced in `bronze_listings`:

  developments              SCD2,   primary_key=venture_id
  listings                  SCD2,   primary_key=listing_id
  zome_developments_state   UPSERT, primary_key=venture_id   (heartbeat sidecar)
  zome_listings_state       UPSERT, primary_key=listing_id   (heartbeat sidecar)
  ref_zome_condition        REPLACE                          (lookup, separate source)
  ref_zome_property_type    REPLACE                          (lookup, separate source)
  ref_zome_business_type    REPLACE                          (lookup, separate source)

SCD2 row versioning is driven by an explicit `row_hash` column over a curated
column subset — JSONB arrays (`gallery`, `raw_json`, etc.) are excluded
because Supabase reorders them between calls and would create false versions.

The heartbeat sidecars are the answer to "is this entity still in the source?"
SCD2 alone cannot distinguish a stable unchanged row from a delisted row.
Silver-layer queries should treat a listing as active when:

    last_seen_date >= current_date - 21

The 21-day floor is: weekly cadence (7) + one missed run (7) + slack (7).
Do not lower it below 14 days. Document any change in the silver model.

Refs are in a separate source (`zome_refs_source`) so a schema drift in any
8-row lookup table cannot abort the 9k-listing facts load.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date
from typing import Any, Iterable

import dlt
from dlt.sources.helpers import requests


SUPABASE_URL = "https://luvskhnljpxllkxpeasu.supabase.co"
PAGE_SIZE = 1000
LISTINGS_MAX_OFFSET = 10_000
RATE_LIMIT_S = 0.5
REQUEST_TIMEOUT_S = 60


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------
#   data_type=freeze  → type drift fails the load loudly (caught the same week)
#   columns=evolve    → new columns land silently as NULL; staging must update
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}


# ---------------------------------------------------------------------------
# Version-relevant columns for SCD2 row_hash. Excluded by design: JSONB arrays
# (reorder noise), display-only fields, immutable identifiers.
# ---------------------------------------------------------------------------
LISTINGS_VERSION_COLUMNS: tuple[str, ...] = (
    "idestadoimovel",
    "idcondicaoimovel",
    "precosemformatacao",
    "precoimovel",
    "valorantigo",
    "areautilhab",
    "areabrutaconst",
    "totalquartossuite",
    "attr_wcs",
    "attr_garagem",
    "attr_garagem_num",
    "attr_elevador",
    "geocoordinateslat",
    "geocoordinateslong",
    "reservadozomenow",
    "showwebsite",
    "showluxury",
)

DEVELOPMENTS_VERSION_COLUMNS: tuple[str, ...] = (
    "preco",
    "precosemformatacao",
    "tipologiagrupos",
    "imoveisdisponiveis",
    "imoveisreservados",
    "imoveisvendidos",
    "exclusividade",
    "idestado",
    "nomeconsultor",
    "emailconsultor",
    "contactoconsultor",
    "deschub",
    "mostrarprecowebsite",
    "geocoordinateslat",
    "geocoordinateslong",
)

# ---------------------------------------------------------------------------
# JSONB columns to keep as `json` data_type, NOT auto-flatten into child tables.
# Addresses dlt issue #3811 (nested-table nondeterminism on schema evolution).
# ---------------------------------------------------------------------------
LISTINGS_JSON_COLUMNS = ("gallery", "raw_json")
DEVELOPMENTS_JSON_COLUMNS = (
    "descricaocompleta",
    "gallery",
    "video",
    "virtualreality",
    "raw_json",
)


# ---------------------------------------------------------------------------
# Field renames — Supabase REST returns these names; bronze uses canonical ones.
# ---------------------------------------------------------------------------
LISTINGS_RENAMES: dict[str, str] = {
    "localizacaolevel1imovel": "localizacaolevel1",
    "localizacaolevel2imovel": "localizacaolevel2",
    "localizacaolevel3imovel": "localizacaolevel3",
    "url_detail_view_website": "url_detail",
}


def _supabase_headers() -> dict[str, str]:
    key = os.environ.get("ZOME_SUPABASE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": "pt_prod",
    }


# ---------------------------------------------------------------------------
# Hashing — canonicalize numerics so int↔float drift from PostgREST does not
# create spurious SCD2 versions. Whitelist scalar types so a non-scalar
# slipping into version_cols fails loudly instead of being str()-stringified.
# ---------------------------------------------------------------------------
_HASH_SCALAR_TYPES = (int, float, str, bool, type(None))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _stable_hash(row: dict, version_cols: Iterable[str]) -> str:
    payload: dict[str, Any] = {}
    for k in version_cols:
        v = row.get(k)
        if not isinstance(v, _HASH_SCALAR_TYPES):
            raise TypeError(
                f"_stable_hash got non-scalar for column {k!r}: {type(v).__name__}. "
                f"Add canonicalization or remove from version_cols."
            )
        payload[k] = _canonicalize(v)
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _fetch_page(path: str, offset: int, limit: int = PAGE_SIZE) -> list[dict]:
    url = f"{SUPABASE_URL}{path}"
    params = {"select": "*", "limit": str(limit), "offset": str(offset)}
    resp = requests.get(
        url, params=params, headers=_supabase_headers(), timeout=REQUEST_TIMEOUT_S
    )
    resp.raise_for_status()
    return resp.json()


def _iter_paginated(path: str) -> Iterable[dict]:
    for offset in range(0, LISTINGS_MAX_OFFSET, PAGE_SIZE):
        rows = _fetch_page(path, offset)
        if not rows:
            return
        yield from rows
        if len(rows) < PAGE_SIZE:
            return
        time.sleep(RATE_LIMIT_S)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def _rename_id(rec: dict, target_key: str) -> dict:
    out = dict(rec)
    if "id" in out:
        out[target_key] = out.pop("id")
    return out


def _normalize_listing(rec: dict) -> dict:
    out = _rename_id(rec, "listing_id")
    for src, dst in LISTINGS_RENAMES.items():
        if src in out:
            out[dst] = out.pop(src)
    out["raw_json"] = rec
    return out


def _normalize_development(rec: dict) -> dict:
    out = _rename_id(rec, "venture_id")
    out["raw_json"] = rec
    return out


# ===========================================================================
# Source 1: Facts (SCD2 + sidecars). Failure here blocks bronze refresh.
# ===========================================================================
@dlt.source(name="zome_facts")
def zome_facts_source() -> Iterable[Any]:
    yield developments
    yield developments_state
    yield listings
    yield listings_state


@dlt.resource(
    name="developments",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="venture_id",
    columns={col: {"data_type": "json"} for col in DEVELOPMENTS_JSON_COLUMNS},
    schema_contract=SCHEMA_CONTRACT,
)
def developments() -> Iterable[dict]:
    for raw in _fetch_page("/rest/v1/tab_ventures", offset=0, limit=PAGE_SIZE):
        rec = _normalize_development(raw)
        rec["row_hash"] = _stable_hash(rec, DEVELOPMENTS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="zome_developments_state",
    write_disposition="merge",
    primary_key="venture_id",
)
def developments_state() -> Iterable[dict]:
    today = date.today()
    load_id = dlt.current.load_id()
    for raw in _fetch_page("/rest/v1/tab_ventures", offset=0, limit=PAGE_SIZE):
        yield {
            "venture_id": raw.get("id"),
            "last_seen_date": today,
            "last_load_id": load_id,
        }


@dlt.resource(
    name="listings",
    write_disposition={
        "disposition": "merge",
        "strategy": "scd2",
        "row_version_column_name": "row_hash",
    },
    primary_key="listing_id",
    columns={col: {"data_type": "json"} for col in LISTINGS_JSON_COLUMNS},
    schema_contract=SCHEMA_CONTRACT,
)
def listings() -> Iterable[dict]:
    for raw in _iter_paginated("/rest/v1/tab_listing_list"):
        rec = _normalize_listing(raw)
        rec["row_hash"] = _stable_hash(rec, LISTINGS_VERSION_COLUMNS)
        yield rec


@dlt.resource(
    name="zome_listings_state",
    write_disposition="merge",
    primary_key="listing_id",
)
def listings_state() -> Iterable[dict]:
    today = date.today()
    load_id = dlt.current.load_id()
    for raw in _iter_paginated("/rest/v1/tab_listing_list"):
        yield {
            "listing_id": raw.get("id"),
            "last_seen_date": today,
            "last_load_id": load_id,
        }


# ===========================================================================
# Source 2: Reference / lookup tables. Loaded as a separate Airflow task so a
# ref schema drift cannot abort the facts load.
#
# NOTE: the exact Supabase REST paths for these lookup tables were not
# documented in the existing pipeline (only the ID→label mappings, in
# README.md lines 280-310). The names below are the most plausible
# PostgREST conventions given the existing `tab_ventures` / `tab_listing_list`
# pattern. If a path is wrong, the refs Airflow task will fail with a 404 —
# the facts load is unaffected. Verify against the Supabase OpenAPI spec
# (GET https://luvskhnljpxllkxpeasu.supabase.co/rest/v1/) and update if needed.
# ===========================================================================
REF_PATHS = {
    "ref_zome_condition": "/rest/v1/tab_condicaoimovel",
    "ref_zome_property_type": "/rest/v1/tab_tipologia",
    "ref_zome_business_type": "/rest/v1/tab_tiponegocio",
}


@dlt.source(name="zome_refs")
def zome_refs_source() -> Iterable[Any]:
    yield ref_zome_condition
    yield ref_zome_property_type
    yield ref_zome_business_type


@dlt.resource(name="ref_zome_condition", write_disposition="replace")
def ref_zome_condition() -> Iterable[dict]:
    yield from _fetch_page(REF_PATHS["ref_zome_condition"], offset=0, limit=PAGE_SIZE)


@dlt.resource(name="ref_zome_property_type", write_disposition="replace")
def ref_zome_property_type() -> Iterable[dict]:
    yield from _fetch_page(REF_PATHS["ref_zome_property_type"], offset=0, limit=PAGE_SIZE)


@dlt.resource(name="ref_zome_business_type", write_disposition="replace")
def ref_zome_business_type() -> Iterable[dict]:
    yield from _fetch_page(REF_PATHS["ref_zome_business_type"], offset=0, limit=PAGE_SIZE)
