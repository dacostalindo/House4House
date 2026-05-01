# ADR 002 — MinIO + PostGIS storage split

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

Why was the project's storage split between MinIO (object storage for raw bronze JSONL/JSON) and PostGIS (relational warehouse for bronze tables, silver, gold)? Why not a single store?

## Decision (TBD)

We use MinIO for raw immutable artifacts (scrape JSONL, API JSON, geo files) and PostGIS for queryable bronze/silver/gold relational data.

## Rejected alternatives (TBD)

- All-PostGIS (TOAST blobs / large text columns).
- All-MinIO (Iceberg / Hudi / Delta Lake table format).
- Cloud object stores (S3 / GCS) instead of MinIO.

## Consequences (TBD)

- Bronze loading pattern: scrape → JSONL to MinIO → INSERT into PostGIS bronze table → dbt downstream.
- Each bronze record carries a `_minio_path` reference for re-replay.
- Cost / operational characteristics.

## References to dig into when filling

- `pipelines/scraping/template/scraping_bronze_template.py` — the canonical bronze-load pattern.
- `pipelines/scraping/template/scraping_ingestion_template.py` — JSONL → MinIO upload.
- `docker-compose.yml` — MinIO + PostGIS service definitions.
- Original commit history when MinIO was first added.
