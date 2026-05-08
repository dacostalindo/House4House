---
title: uv workspace shape — single root, apps + pipelines members
type: decision
last_verified: 2026-05-08
tags: [uv, workspace, packaging, infra]
confidence: high
---

## For future Claude

This is a decision record about the uv workspace layout chosen during the Phase 1 spike. It locks in the single-root-with-members topology (apps + pipelines as workspace members) over the briefly-considered "two independent projects" alternative. Read this when adding a new top-level package, debugging cross-member import errors, or considering splitting the workspace.

## Decision

House4House uses a **uv workspace** with a single root `pyproject.toml` declaring two members: `apps/` (Streamlit + analytical tooling) and `pipelines/` (Airflow DAGs + dlt resources + scrapers + GIS ingest). One root `uv.lock` resolves the unified dep graph for both members.

Per-member install via `uv sync --group <member>` keeps Docker images scoped — the Airflow image installs only `pipelines/` deps, the Streamlit image installs only `apps/` deps.

## Why

Two competing topologies were on the table during the Phase 1 spike:

- **Workspace** (chosen): single root `pyproject.toml` + workspace members; one lockfile; per-member install groups.
- **Two independent projects**: separate `apps/pyproject.toml` and `pipelines/pyproject.toml`, each with its own lockfile; no shared dep graph.

The workspace won because the cost of split-projects was concrete: separate lockfiles meant separate version-resolution for shared deps (PostgreSQL drivers, GeoPandas, Pydantic), creating drift hazards. The Phase 1 spike found that apps had zero SQLAlchemy code despite Airflow forcing SQLA <2.0 — meaning the workspace can pin SQLA 1.4 globally without hurting apps, which would NOT be possible cleanly with two independent lockfiles trying to resolve compatible-but-different SQLA versions.

The "single powerful server" deployment posture (per README §3.2) reinforces the workspace choice: one machine running both apps and pipelines benefits from a unified Python env on the host (when not containerized).

## Options considered

1. **uv workspace, single root, two members** (chosen) — single lockfile, per-member install groups, unified dep resolution.
2. **Two independent uv projects** (rejected) — separate `pyproject.toml` per directory, independent lockfiles. Rejected due to (a) dep-drift risk on shared libs, (b) [[2026-05-08-sqla-1.4-concession]] would have required manual coordination.
3. **Monolithic single-package layout** (rejected as out-of-scope) — collapse apps/pipelines into one flat package. Would have made Docker-image scoping (apps-only vs pipelines-only deps) impossible.

## Consequences

- One `uv sync` resolves the full graph; one `make verify` runs against it.
- Cross-member imports work transparently; a future `apps/` page can import from `pipelines.common.SCD2_RULES` if needed.
- A single dep upgrade (e.g., `pydantic 2.x → 2.y`) coordinates across both members or fails the resolution loudly.
- Docker scope discipline is enforced via `uv sync --group <member>` — accidentally bloating the Airflow image with Streamlit deps (or vice versa) requires explicit Dockerfile change.
- The [[2026-05-08-sqla-1.4-concession]] downstream of this decision: the workspace's unified resolution forces apps to accept SQLA 1.4 globally (zero apps-side cost confirmed during spike).

## Status

`accepted` — Phase 1 shipped; baseline holds across Phase 2 and Phase 3 PR 1. High confidence; battle-tested through two phases.

## See also

- [[2026-05-08-sqla-1.4-concession]] — the SQLAlchemy version concession enabled by this workspace shape
- [[2026-05-05-cosmos-pin]] — the Cosmos pin that constrains the workspace's Airflow side
- [[airflow-home-isolation]] — the gotcha discovered during the Phase 1 spike that produced this decision
- [[medallion-layering]] — the architecture this workspace serves
