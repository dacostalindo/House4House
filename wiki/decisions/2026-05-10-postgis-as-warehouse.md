---
title: PostgreSQL + PostGIS as the warehouse (not Snowflake / BigQuery)
type: decision
last_verified: 2026-05-10
tags: [warehouse, postgis, infra, decision]
confidence: high
---

## For future Claude

This is a decision record about using PostgreSQL 16 + PostGIS 3.4 as the data warehouse, rejecting cloud-native warehouses (Snowflake, BigQuery, Redshift) and managed Postgres (RDS, Cloud SQL). It locks in the spatial-first / cost-aware shape. Read this when scoping a warehouse migration, evaluating a new analytical workload, or considering whether a use case justifies cloud-warehouse cost.

## Decision

The warehouse is **PostgreSQL 16 + PostGIS 3.4**, deployed self-hosted (Docker on a single Hetzner AX102 — see [[2026-05-10-single-server-self-hosted]]). All bronze/silver/gold layers (per [[medallion-layering]]) live in this single Postgres instance. No cloud warehouse, no managed Postgres.

## Why

Three load-bearing claims:

1. **Spatial workloads benefit enormously from PostGIS specifically.** Listings × parcels × census × constraints × OSM queries are the project's hot path (UC-1 / UC-2 / UC-3 all spatial-join-intensive). PostGIS has 20+ years of spatial-index maturity; cloud warehouses retrofit spatial as an afterthought (BigQuery's GEOGRAPHY support is functional but slower than PostGIS for the parcel-grain queries we run).
2. **Solo-dev cost matters.** Self-hosted Postgres on a Hetzner box: ~€85/month (the box itself, including 128 GB RAM and 4 TB NVMe). Snowflake equivalent: ~$300-500/month minimum. RDS Postgres + RAM equivalent: ~€600/month. The cost ratio compounds across years.
3. **No cloud-warehouse capability is essential to the workload.** We don't need petabyte scaling, multi-region replication, separate compute / storage scaling, or always-on warm standbys. Single-server Postgres with `shared_buffers=8GB` + `effective_cache_size=24GB` keeps the working set hot in RAM for our actual workload size (~100 GB of bronze, ~50 GB silver/gold).

## Options considered

1. **PostgreSQL + PostGIS, self-hosted** (chosen) — see Decision.
2. **AWS RDS PostgreSQL + PostGIS** — managed Postgres with PostGIS extension. Rejected on cost (~7× self-hosted) and on operational unfamiliarity (we'd debug RDS-specific quirks like backup-window stalls instead of having full local control).
3. **Google Cloud SQL** — same shape as RDS. Rejected for same reasons.
4. **Snowflake** — would require swapping PostGIS for Snowflake's native GEOGRAPHY/GEOMETRY support. Spatial functions exist but are slower for the parcel-grain workload + cost compounds with compute-on-demand. Solo-dev shouldn't be optimizing for petabyte scaling.
5. **BigQuery + GEOGRAPHY** — same as Snowflake. Plus query-cost surprise risk that doesn't fit the steady-state operations posture.
6. **DuckDB as primary** — DuckDB has good spatial support (DuckDB Spatial extension) and would be cheaper still. Rejected because DuckDB is single-process; serving Streamlit + Metabase + Airflow concurrent reads from one DuckDB file produces lock contention. Kept DuckDB as a SUPPLEMENT for fast Parquet scans; not the primary store.

## Consequences

- All silver + gold transformations are SQL via dbt + Cosmos (no in-memory analytics framework).
- Backups are `pg_dump` to MinIO daily (per [[orchestration]]'s maintenance DAGs). Recovery is restore-from-dump.
- Schema deltas land via dbt migrations + occasional `warehouse/init/*.sql` patches; no managed-Postgres "click-to-add-column" UX.
- Spatial query performance depends on PostGIS-specific index discipline (`GIST`, `SP-GIST` per use case). Documented per-table in dbt model SQL files.
- A future migration to a cloud warehouse becomes a real project: the dbt models would need spatial-function rewrites + bronze-load adapter changes. No current trigger.

## Status

`accepted` — Phase 1 baseline holds; all 23 sources operate against this warehouse without observed perf issues at current data volume. High confidence.

## See also

- [[2026-05-10-single-server-self-hosted]] — the single-server posture this decision sits on
- [[2026-05-10-minio-not-s3]] — companion decision for raw landing
- [[medallion-layering]] — the bronze/silver/gold layout served
- [[infra]] — Docker Compose service map showing where Postgres runs
- [[tech-stack]] — primary stack table
- README §3.1 + §4.3 — the canonical source for this content
