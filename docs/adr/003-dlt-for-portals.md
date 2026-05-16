# ADR 003 — dlt for the three portal pipelines

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

The three portal pipelines (RE/MAX, Idealista, Zome) use the `dlt` (data load tool) library for ingestion + SCD2 management. Other pipelines use the simpler `BronzeTableConfig` pattern (or hand-rolled DAGs).

What problem prompted introducing dlt? What were the trade-offs?

## Decision (TBD)

We use dlt for portal ingestion. Specifically: dlt's resource pattern + SCD2 merge strategy + schema contracts.

## Rejected alternatives (TBD)

- Custom SCD2 logic in `BronzeTableConfig` (hand-rolled).
- dbt snapshots (PostgreSQL-side SCD2).
- Airbyte / Meltano / other ingestion frameworks.

## Consequences (TBD)

- Schema contract (`{"data_type": "freeze"}`) catches type drift; new columns silently NULL.
- `row_hash` over curated `*_VERSION_COLUMNS` drives diff detection.
- Per-portal heartbeat (state) sidecars track `last_seen_date`.
- dlt-managed columns (`_dlt_valid_from`, `_dlt_valid_to`, `_dlt_load_id`, `_dlt_id`) appear in every fact table.
- Operational cost (dlt processes are heavier than the BronzeTableConfig pattern).

## References to dig into when filling

- `pipelines/portals/{remax,idealista,zome}/source.py` — dlt resource definitions.
- `wiki/concepts/scd2-row-hash.md` — version-column policy.
- `archive/portal_dlt_cutover_2026/` — original cutover plans (path refs are pre-rename).
- Compare with `pipelines/api/{bpstat,ecb,eurostat,ine}/` (non-dlt pattern).
