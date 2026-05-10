---
title: dbt for transformations (not SQLModel)
type: decision
last_verified: 2026-05-10
tags: [dbt, transformations, sqlmodel, decision]
confidence: high
---

## For future Claude

This is a decision record about using dbt Core (with Cosmos for Airflow integration) for all bronze→silver→gold transformations, rejecting SQLModel as an alternative. The choice was specifically debated during the dev-tooling design's eng-review pass and then made explicit. Read this before considering a transformation-layer change, or when asked "why dbt rather than ORM-style models?"

## Decision

All bronze→silver→gold transformations are SQL via **dbt Core 1.7+**, orchestrated by Cosmos 1.6 inside Airflow. Models live in `dbt/models/{staging,silver,gold}/<domain>/`. SQLModel is not used for transformation logic anywhere in the project.

(SQLModel may still appear in `apps/` for application-layer data access, but it does NOT participate in transformations or warehouse modelling.)

## Why

1. **dbt's `ref()` graph is the load-bearing abstraction.** Lineage, dependency-aware execution, dbt-utils tests, dbt-docs all flow from the `ref()`-resolved model graph. SQLModel has no equivalent — it's an ORM, not a transformation framework.
2. **Cosmos auto-generates Airflow task graphs from dbt's manifest.** Per [[orchestration]] + [[2026-05-05-cosmos-pin]], the dbt-task-graph maps directly to Airflow tasks. Switching to SQLModel-driven transformations would require us to manually maintain the Airflow task graph (one task per silver/gold model) — that's ~150 lines of DAG-orchestration code per dbt project replicated by hand, brittle on every model add/remove.
3. **Tests live next to models, not in a separate test framework.** dbt's `schema.yml` + `dbt_utils.accepted_range` etc. (per [[data-quality]]) keep tests co-located with the models they validate. SQLModel-driven transformations would need a separate Pydantic-based test layer that doesn't natively integrate with the warehouse.
4. **dbt's documentation surface is genuinely useful.** `dbt docs serve` produces a navigable graph + per-model column-level documentation that doubles as wiki content. SQLModel has no equivalent.
5. **Solo-dev should not be writing transformation orchestration by hand.** The "not invented here" cost of replacing dbt with hand-rolled SQLModel + custom orchestration is enormous; the savings are zero.

## Options considered

1. **dbt Core + Cosmos** (chosen) — see Decision.
2. **dbt Cloud** — managed dbt with web IDE + scheduling. Rejected on cost (~$100+/month for solo-dev) + we already have Airflow + Cosmos providing the scheduling layer cheaper.
3. **SQLModel** — Python-native, type-safe SQL access via Pydantic + SQLAlchemy. Rejected because it's solving a different problem (application-layer data access vs. warehouse transformations). Trying to use SQLModel as a transformation framework reinvents the dbt graph + tests + docs by hand.
4. **SQLMesh** — newer dbt-alternative with stronger Python integration + native time-travel. Considered briefly during eng-review. Rejected for current Phase because (a) Cosmos integration is mature for dbt, immature for SQLMesh, (b) ecosystem maturity favors dbt for solo-dev (more StackOverflow Q's, more provider patterns, more tutorials), (c) no SQLMesh-specific feature is essential to UC-1/2/3.
5. **Pure Python (Pandas / Polars / SQLAlchemy raw queries)** — feasible but reinvents transformation orchestration + tests + lineage by hand. Rejected as a non-starter.

## Consequences

- All silver + gold models are `.sql` files following dbt conventions.
- Tests are declared in `schema.yml` alongside models (per [[data-quality]]).
- Cosmos's `DbtDag` auto-generates the task graph from the dbt manifest; one Airflow task per dbt model.
- A future SQLMesh migration is conceivable but not cheap: dbt models would re-author, test framework re-implements, Cosmos integration replaced by SQLMesh's own orchestration adapter.
- The Pydantic-AI Phase 5 enrichment (per [[2026-05-08-idealista-enrichment-architecture]]) writes to silver via a Python-side dlt pipeline — NOT via dbt — because LLM output flow is a structured-data ingest pattern, not a SQL transformation. This split is intentional.

## Status

`accepted` — Phase 1 + Phase 2 + Phase 3 PR 1-5 all use dbt for transformations. Production-stable. High confidence.

## See also

- [[2026-05-05-cosmos-pin]] — the Cosmos pin tied to this stack
- [[medallion-layering]] — bronze/silver/gold rationale; dbt is the silver+ engine
- [[data-quality]] — dbt tests on top of dbt models
- [[bronze-permissive]] — bronze does NOT use dbt (dlt's job); dbt starts at silver
- [[orchestration]] — Airflow + Cosmos integration
- [[tech-stack]] — primary stack table
- [[2026-05-08-idealista-enrichment-architecture]] — Phase 5 enrichment exception (Python dlt → silver, NOT dbt)
- README §3.1 — the canonical source for this content
