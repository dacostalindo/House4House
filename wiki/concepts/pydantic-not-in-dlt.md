---
title: Pydantic NOT in dlt resources
type: concept
last_verified: 2026-05-08
tags: [pydantic, dlt, bronze, validation, guardrail]
---

## For future Claude

This is a concept page about the strict guardrail "Pydantic models live in pipeline configs, NEVER inside dlt resources or `columns=` hints." It explains the asymmetry (config = strict; bronze ingest = permissive), why dlt's history of v1↔v2 friction makes the rule defensive, and how this rule fits with [[bronze-permissive]]. Read this when migrating a config to Pydantic (Phase 2 work), when tempted to add a Pydantic model to a dlt resource for "safety," or when reviewing any new `*_config.py`.

## What it is

A two-line rule:

1. **Pipeline configs (`*_config.py`)**: Pydantic v2 `BaseModel` is the right tool. Type-annotate fields, use validators, expect strict input. Configs are project-internal contracts and benefit from strictness.
2. **dlt resources / `columns=` hints / scrapers**: Pydantic is **forbidden**. Use plain dicts, raw JSON, or dlt's own dataclass-style schema declaration. Bronze ingest follows [[bronze-permissive]].

The asymmetry is deliberate.

## Why

Two reasons, both backed by historical pain:

**1. Bronze-permissive constraint** ([[bronze-permissive]]): bronze must accept whatever the source returns, including upstream regressions, type drift, and field renames. Pydantic's `model_validate()` raises on any drift — using it inside a dlt resource means the day the source ships a string where you expected int, the entire load fails and you have no record of what the source actually returned. Bronze permissive + staging-strict is the right split.

**2. dlt v1.x had Pydantic v1↔v2 friction historically.** dlt 1.25 supports Pydantic v2 cleanly, but earlier versions had subtle resolution issues (model fields not flattening, JSONB columns being mishandled, pickle/serialization edges with custom validators). The rule "no Pydantic in dlt resources" was set defensively and has held because the next time dlt has a major version bump, the rule keeps us from a fragile coupling layer.

The Phase 2 spec made this guardrail explicit because Pydantic was being adopted across the codebase and the natural temptation is "well if configs use Pydantic, why not the dlt resources too?" The answer is "because configs are project-internal, dlt resources interface with a moving target."

## How

**Where Pydantic IS the right answer:**

- `pipelines/portals/idealista/idealista_config.py` — yes, Pydantic
- `pipelines/api/ine/ine_config.py` — yes
- `pipelines/gis/srup_ogc/srup_ogc_config.py` — yes
- Any Phase 5 enrichment schema (`ListingEnrichment` for [[idealista]] description parsing) — yes

**Where Pydantic is forbidden:**

- `pipelines/portals/idealista/source.py` (the dlt source) — NO
- Any `dlt.resource(columns=...)` — NO. Use dlt's own column declarations.
- Scraper-output rows before they enter dlt — NO.
- The schema-contract block (`SCHEMA_CONTRACT`) — that's dlt's, not Pydantic's.

**dbt staging is where validation lands**: type casts, NULL guards, range checks, enum-membership tests. dbt-utils provides the test framework; `dbt build` runs it on every PR via [[medallion-layering]] CI.

**Test fixtures lock configs in place**: each Pydantic config has a JSON snapshot fixture under `tests/configs/fixtures/<source>.json` that asserts the schema doesn't drift accidentally. Pre-migration snapshots were captured during Phase 2 work; comparing post-migration output against snapshot caught a couple of subtle field-rename regressions.

**Failure mode if violated**: if a Pydantic model creeps into a dlt resource, the symptoms are (a) upstream schema drift kills the entire load instead of capturing it in bronze for inspection, (b) the dlt-version bump in some future Phase produces a confusing error about model resolution. Both are recoverable but slow.

## See also

- [[bronze-permissive]] — the policy this rule operationalizes
- [[scd2-row-hash]] — operates within bronze-permissive (no Pydantic)
- [[idealista]], [[jll]], [[remax]], [[zome]] — every dlt portal pipeline observes this rule
- [[ine]], [[bpstat]], [[ecb]], [[eurostat]] — API pipelines whose configs ARE Pydantic
- pipelines/CLAUDE.md — the area-routing file that enforces this on edits
