# ADR 005 — JSONB sidecar columns vs full normalization

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

Bronze tables for the three portals carry JSONB sidecar columns (galleries, room arrays, raw API payloads, equipment lists). Why keep these as JSONB rather than flatten into child tables?

## Decision (TBD)

We keep nested arrays/objects as JSONB columns with `data_type: "json"` schema-contract hint, NOT as auto-flattened dlt child tables.

Specifically:
- Image arrays (`gallery`, `building_pictures`, `listing_pictures`, `property_images`).
- Per-room area breakdowns (`listing_rooms`).
- Feature/equipment arrays (`property_features`, `property_equipment`, `listing_attributes_ids`).
- Raw payload escape hatches (`raw_json`, `raw_meta`).
- Region hierarchy (`location_hierarchy`, `regiao`).
- Multi-language descriptions (`descricaocompleta`).

## Rejected alternatives (TBD)

- Auto-flatten to child tables (dlt default behavior). Caused nondeterministic schema evolution per dlt issue #3811 — child table names depended on first-seen object keys, churned across runs.
- Hand-built normalized schema per nested structure (gallery_image, property_feature tables).

## Consequences (TBD)

- JSONB columns are explicitly excluded from `row_hash` (they cause spurious SCD2 versions when API reorders).
- Downstream silver work needs `jsonb_array_elements()` / JSONB path expressions to extract.
- Trade-off: ergonomic for ingestion, slightly less ergonomic for silver. Acceptable since silver runs less often than ingestion.

## References to dig into when filling

- dlt issue #3811 — original justification.
- `pipelines/portals/*/source.py` — *_JSON_COLUMNS definitions per portal.
- `pipelines/common/SCD2_RULES.md` — JSONB exclusion rules.
- Sample silver model that consumes a JSONB column (when one exists post-Sprint 4.5).
