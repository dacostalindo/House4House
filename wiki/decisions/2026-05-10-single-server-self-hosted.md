---
title: Single-server self-hosted deployment (not multi-server / cloud)
type: decision
last_verified: 2026-05-10
tags: [infra, deployment, self-hosted, decision]
confidence: high
---

## For future Claude

This is the **load-bearing infrastructure decision** for the project — single Hetzner AX102 (or equivalent), self-hosted Docker Compose stack, no multi-server topology, no cloud-managed services. Six other ADRs cascade from this one ([[2026-05-10-postgis-as-warehouse]], [[2026-05-10-minio-not-s3]], [[2026-05-10-airflow-2-not-3]], [[2026-05-10-dbt-not-sqlmodel]], [[2026-05-10-nominatim-osrm-self-hosted]], [[2026-05-10-metabase-streamlit-not-superset]] — all "we self-host because we self-host the substrate"). Read this when scoping a deployment, considering a multi-region future, or evaluating whether a use case justifies cloud cost.

## Decision

House4House deploys as a **single Docker Compose stack on a single self-hosted server** (Hetzner AX102 or equivalent: 16 cores, 128 GB RAM, 2× 2TB NVMe, ~€85/month). All services co-resident: PostgreSQL + PostGIS warehouse, MinIO object store, Airflow, Cosmos, Metabase, Streamlit, Nominatim, OSRM, Selenium. No multi-server topology. No cloud-managed services.

## Why

Three load-bearing claims:

1. **Spatial workloads benefit enormously from local I/O and memory.** PostGIS queries against [[bgri]]'s 200k census subsections, [[bupi]]'s 3.25M parcels, and [[osm]]'s 4.5M features perform at memory-resident speeds when Postgres sits on the same NVMe slot as the data, with `shared_buffers=8GB` + `effective_cache_size=24GB` keeping the working set hot. Cloud-managed Postgres trades that for elastic scaling we don't need.
2. **Cloud egress costs add up fast with large GIS datasets.** [[osm]] is ~1.5 GB monthly; [[bupi]] is ~600 MB; [[bgri]] is ~459 MB; [[lidar]] is ~1 GB. Mirroring + reading back across S3 + EC2 boundaries: ~$0.10/run × 30 sources × monthly cadence ≈ ~$36/year just in egress. Plus per-request charges on every Airflow task that reads from S3. Self-hosted: ~€0 incremental.
3. **Solo-dev operations is doable on a single Hetzner AX102.** ~€85/month for 16 cores / 128 GB / 4 TB NVMe is unbeatable on a $/RAM basis. Cloud-equivalent compute (e.g., AWS r6i.4xlarge with similar RAM): ~€500-900/month + storage + network. ~10× cost ratio.

**Could change if:**
- Multi-region serving becomes a need (no current trigger; PT-only for the foreseeable future).
- A team forms (operational overhead becomes worth offloading).
- Spatial data volume crosses ~1 TB working set (single-NVMe-pair becomes the bottleneck; data > RAM forces disk-paging that cloud-managed warehouses handle better).
- An SLA / uptime requirement emerges that needs multi-AZ failover.

None of those are in scope for current Phases.

## Options considered

1. **Single self-hosted server (Hetzner AX102)** (chosen) — see Decision.
2. **Multi-server self-hosted** — separate Postgres / Airflow / MinIO machines. Rejected: the workload doesn't benefit from physical separation at current volume + adds operational complexity (replication, network latency, cross-host Docker networking).
3. **Cloud-managed (AWS RDS + S3 + MWAA + RedShift / BigQuery)** — rejected on cost (~10× more). Solo-dev is the load-bearing constraint.
4. **Cloud-managed compute, self-hosted storage** (e.g., Hetzner for Postgres, AWS S3 for raw landing) — rejected because the egress cost of reading bulk-data raw files back from S3 is what hurts; keeping both local on the same box is what makes it cheap.
5. **Kubernetes self-hosted** — would add reproducibility + auto-restart + better resource isolation. Rejected because Docker Compose suffices for the current workload + K8s ops overhead is real for solo-dev.

## Consequences

- Hardware failure = full outage. Acceptable: no SLA exists. Backups: daily `pg_dump` to MinIO + weekly server snapshot to a second drive.
- Capacity ceiling: NVMe slot capacity (~4 TB), RAM (128 GB), CPU (16 cores). Trigger for upgrade: >80% NVMe utilization OR Postgres `effective_cache_size` saturation.
- Six other infra ADRs cascade from this:
  - [[2026-05-10-postgis-as-warehouse]] — PostGIS, not Snowflake.
  - [[2026-05-10-minio-not-s3]] — MinIO, not S3.
  - [[2026-05-10-airflow-2-not-3]] — Airflow 2.10 self-hosted, not MWAA.
  - [[2026-05-10-dbt-not-sqlmodel]] — dbt Core CLI, not dbt Cloud.
  - [[2026-05-10-nominatim-osrm-self-hosted]] — Nominatim + OSRM, not Google Maps APIs.
  - [[2026-05-10-metabase-streamlit-not-superset]] — Metabase + Streamlit, both self-hosted.
- A future cloud migration is a multi-month project: every cascading ADR re-decides; data + service migration plans needed; cost model changes from "fixed €85/month" to "variable cloud bill."

## Status

`accepted` — Phase 1 + Phase 2 + Phase 3 PR 1-5 all run on this baseline. Production-stable. High confidence; foundational decision that hasn't shifted in 3+ months of iteration.

## See also

All six cascading ADRs above. Plus:

- [[infra]] — Docker Compose service map + server spec
- [[tech-stack]] — primary stack table
- [[overview]] — 1-page project synthesis
- README §3.2 + §4 + §15 (Resource Requirements) — the canonical source for this content
