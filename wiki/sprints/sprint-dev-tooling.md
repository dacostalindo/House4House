---
title: Sprint dev-tooling — gstack-driven 7-Phase roadmap
type: plan
last_verified: 2026-05-09
tags: [sprint, plan, dev-tooling, gstack, parallel-track]
status: in_progress
sprint_number: "dev-tooling"
weeks: "parallel"
last_status_update: 2026-05-09
---

## For future Claude

This is the **dev-tooling sprint** — a single page consolidating the gstack-driven 7-Phase roadmap that ran in parallel with the data-product sprints (Sprint 1-9). Phase 1 (uv workspace) + Phase 2 (Pydantic configs) shipped 2026-Q1; Phase 2.5 closed by audit (no work to do); Phase 3 (Claude Code + LLM Wiki) is in flight (PR 1 + PR 2 + this PR shipped); Phases 4-7 are planned. Read this when you need to know what dev-tooling infrastructure exists today, what's coming, and which ADRs/concepts came out of each Phase.

Per `/plan-eng-review` finding 1.5: a single `status:` field can't capture multi-Phase state (4 done + 1 in_progress + 3 planned). Frontmatter says `status: in_progress` (the overall workstream is active); the **Phase status table** below is the source of truth for which specific Phases shipped when.

## Goal

Build the dev-tooling foundation that makes the data-product sprints faster, safer, and self-documenting: deterministic Python workspace ([[2026-05-05-uv-workspace-shape]]), Pydantic strict configs at the boundary ([[pydantic-not-in-dlt]]), karpathy-style LLM Wiki for compounding project knowledge, CI/CD with mechanical lint gates, LLM-driven feature enrichment with strict-output-schema, advisory type checking, and codified Claude Skills for repetitive scaffolding tasks.

The parallel structure: data-product sprints ship product features; dev-tooling Phases ship the substrate those features run on. Both compound.

## Deliverables — by Phase

See the Phase status table below for current state. Each Phase's deliverables are ADRs + concept pages + commits referenced via `[[wikilinks]]`.

## Phase status table

| Phase | Description | Status | Shipped | Key artifacts |
|---|---|---|---|---|
| Phase 1 | uv workspace + Ruff sweep + Airflow isolation gotcha | ✅ done | 2026-Q1 | [[2026-05-05-uv-workspace-shape]], [[2026-05-05-cosmos-pin]], [[airflow-home-isolation]], [[2026-05-08-sqla-1.4-concession]] |
| Phase 2 | Pydantic v2 BaseModel configs (4 source configs migrated: idealista, srup, crus, cadastro) | ✅ done | 2026-Q2 | [[pydantic-not-in-dlt]], snapshot test fixtures at `tests/configs/fixtures/{idealista,srup,crus,cadastro}.json` |
| Phase 2.5 | (originally: sweep ALL inline validators to Pydantic) — ABSORBED by Phase 2 audit | ✅ closed | 2026-05-08 | [[2026-05-08-phase-2-5-closure]] (audit found 0 Pydantic-eligible sites among 90 actual call sites; closure is the deliverable) |
| Phase 3 | Claude Code integration + LLM Wiki (CLAUDE.md hierarchy + wiki/ + /wiki-lint + post-merge gstack-ingest convention) | 🔄 in_progress | partial | PR 1 (scaffold), PR 2 (seed), PR 3 (sprints + this page); PR 4-7 (use cases, sources priorities, architecture, planning) coming |
| Phase 4 | CI/CD bootstrap + `scripts/wiki_health.py` BLOCKING lint + Phase 1 README cleanup verifier + pointer-table-discipline check | planned | — | Will land: `make wiki-lint-fast`, `wiki_health.py` with `[[wikilinks]]` resolution, frontmatter schema validation, sprint Status update history regex enforcement, decisions/ confidence enum check, supersedes/superseded_by reciprocal validation |
| Phase 5 | [[idealista]] description enrichment via Pydantic AI ([[2026-05-08-idealista-enrichment-architecture]] locked: `ListingEnrichment` schema; writes to silver, NOT bronze; description-hash idempotency cache; dead-letter table for parse failures) | planned | — | Couples to Sprint 5 hedonic features (energy-class enrichment); runs in parallel with data-product sprint |
| Phase 6 | `ty` advisory type-check (Astral's static type-checker for Python; advisory-only initially; graduates to BLOCKING via TODO trigger) | planned | — | Adds `ty check` to `make verify` + CI as `continue-on-error: true`; Phase 4e CI annotation grouping (per `/plan-devex-review` G5) tags ty findings as `[ty]` |
| Phase 7 | Claude Skills: `/add-gis-source`, `/add-portal-source`, `/stg-from-bronze`, `/wiki-reconcile`, `/wiki-import-gstack` | planned | — | Skills codify scaffolding patterns 3-5x done manually; `/wiki-reconcile` is interactive-only (per `/plan-devex-review` G1); `/wiki-import-gstack` is the Phase 7e structured-ingest skill that closes the post-merge gstack-ingest convention loop |

## Exit criteria

Per Phase, locked at the time the Phase shipped:

- Phase 1: `make verify` returns green; `make setup` works on a fresh checkout; idealista DAG runs unchanged after Ruff `--fix` autofixes against staging DB. Met 2026-Q1.
- Phase 2: 4 source configs migrated to Pydantic v2; snapshot test fixtures locked; `make verify` includes the snapshot test. Met 2026-Q2.
- Phase 2.5: audit finds zero Pydantic-eligible sites; design doc updated to `ABSORBED BY PHASE 2`. Met 2026-05-08.
- Phase 3: `wiki/` exists with schema in CLAUDE.md; PR 1 scaffold + PR 2 seed shipped; CLAUDE.md hierarchy at root + per-area routes Claude to relevant concepts; weekly `/wiki-lint` cron operational. Pending: PR 3 (this) + PR 4-7 + PR 8 README stub.
- Phase 4-7: see each Phase's spec in this page's body (the gstack `dev-tooling-design.md` snapshot was folded in during PR 3; this page is now the canonical roadmap surface).

## Key decisions

The dev-tooling roadmap is decision-rich. Top decisions (each linked to its ADR):

- [[2026-05-05-uv-workspace-shape]] — single root pyproject + apps/pipelines members; one lockfile; per-member install groups.
- [[2026-05-05-cosmos-pin]] — `astronomer-cosmos>=1.6,<1.7`. 1.7+ imports `airflow.sdk` (Airflow-3-only).
- [[2026-05-08-sqla-1.4-concession]] — apps/ accepts workspace-wide SQLAlchemy 1.4 because Airflow 2.10 forces <2.0; apps had zero SQLA code (audit-confirmed).
- [[2026-05-08-phase-2-5-closure]] — Phase 2.5 closed with no work; audit found 90 inline validators of which 0 were Pydantic-eligible (control-flow guards or [[bronze-permissive]]-forbidden external-data validation).
- [[2026-05-08-idealista-enrichment-architecture]] — three coexisting [[idealista]] streams; Phase 5 LLM-driven enrichment writes to silver, NOT bronze.
- 9 README-derived stack ADRs land alongside Phase 4 (PR 6 of the wiki migration): postgis-as-warehouse, minio-not-s3, airflow-2-not-3, dbt-not-sqlmodel, nominatim-osrm-self-hosted, streamlit-keplergl-not-superset, single-server-self-hosted, dbt-tests-plus-great-expectations, metabase-streamlit-split.

## Status update history

- 2026-05-05: declared in gstack design doc (since folded into this page; original snapshot at d26e31e was DELETED in PR 3 commit 3a)
- 2026-Q1: Phase 1 → done (uv workspace + Ruff sweep + airflow-home isolation gotcha)
- 2026-Q2: Phase 2 → done (Pydantic configs migrated; snapshot tests added)
- 2026-05-08: Phase 2.5 → closed (audit finding documented in [[2026-05-08-phase-2-5-closure]])
- 2026-05-08: Phase 3 PR 1 → done (wiki scaffold + CLAUDE.md hierarchy + /wiki-lint cron)
- 2026-05-08: Phase 3 PR 2 → done (23 source pages + 8 concept pages + 5 ADRs + overview.md)
- 2026-05-09: Phase 3 PR 3 (this PR) → in_progress (sprints + dev-tooling sprint + folder relocation + wiki/README.md trunk-test refresh)

## See also

- [[2026-05-05-uv-workspace-shape]], [[2026-05-05-cosmos-pin]], [[2026-05-08-sqla-1.4-concession]], [[2026-05-08-phase-2-5-closure]], [[2026-05-08-idealista-enrichment-architecture]] — the 5 ADRs that came out of Phase 1+2+2.5+3
- [[airflow-home-isolation]], [[pydantic-not-in-dlt]], [[bronze-permissive]], [[scd2-row-hash]], [[heartbeat-sidecar]], [[medallion-layering]], [[zenrows-universal-vs-re-api]], [[payload-cache-lifecycle]] — the 8 concept pages distilled during Phase 3 PR 2
- [[overview]] — 1-page project synthesis (built during Phase 3 PR 2)
- [[sprint-01]] — parallel data-product sprint that ran alongside Phase 1
- [[sprint-04]] — parallel data-product sprint where image classification + SCE work landed alongside Phase 3
- [[sprint-05]] — parallel data-product sprint where Phase 5 description enrichment will couple in
