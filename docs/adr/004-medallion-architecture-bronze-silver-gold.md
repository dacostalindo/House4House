# ADR 004 — Medallion architecture (bronze / silver / gold)

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

The project follows a three-tier data architecture: bronze (raw ingestion), silver (cleaned and joined), gold (analytics-ready). Why this split vs alternatives?

## Decision (TBD)

We use medallion (bronze → silver → gold) with each tier in its own Postgres schema (`bronze_listings`, `silver_properties`, `gold_analytics`, etc.) and dbt-built silver/gold layers.

## Rejected alternatives (TBD)

- Two-tier: raw + serving (skip silver).
- ELT directly into a serving schema (no clear lifecycle separation).
- Data vault (hubs / links / satellites).

## Consequences (TBD)

- dbt schema discovery via `+schema` configs in `dbt_project.yml`.
- Bronze tables append-only (history-preserving); silver dedupes; gold aggregates.
- Cosmos per-source DAGs trigger silver/gold transformations after bronze load.
- Schema naming convention enforces tier identity.

## References to dig into when filling

- `dbt/dbt_project.yml` — schema configs.
- `dbt/macros/get_custom_schema.sql` — schema-name override macro.
- README.md — Layer 1–6 architecture diagram.
- `pipelines/dbt/dbt_source_dags.py` — per-source Cosmos triggers.
