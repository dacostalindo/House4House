---
title: Bronze-permissive policy
type: concept
last_verified: 2026-05-08
tags: [bronze, dlt, validation, medallion, policy]
---

## For future Claude

This is a concept page about the bronze-permissive policy — the rule that bronze ingest accepts whatever the source returns (no Pydantic validation, no type coercion, no field renaming inside dlt) and pushes all type discipline down to dbt staging. It explains why [[pydantic-not-in-dlt]] is the strict corollary, the schema-contract escape valve (`data_type=freeze, columns=evolve`), and the never-delete-from-bronze invariant. Read this when adding any dlt resource, deciding where validation belongs, or being asked "should I add a Pydantic model to this scraper?"

## What it is

Bronze-permissive is the policy that **bronze tables accept whatever the source returns, faithfully and without judgment**. The dlt resource:

- Does NOT validate field types, ranges, enum values, or required-presence
- Does NOT rename fields, coerce strings to numbers, or drop "junk" columns
- Does NOT use Pydantic models on incoming rows ([[pydantic-not-in-dlt]])
- DOES freeze the schema shape via dlt's `SCHEMA_CONTRACT` (type drift on a known column → loud failure)
- DOES skip stub-shaped degraded payloads ([[scd2-row-hash]] stub-handling) but emits a [[heartbeat-sidecar]]

All cleanup, type discipline, and field renaming happens **downstream in dbt staging models** (`stg_*.sql`).

## Why

Three reasons, each from real incidents:

1. **Bronze must be able to capture upstream regressions silently** so we can detect them. If the dlt resource enforces "price must be int", then a day when the source switches to string-formatted prices fails the load — and we have no record of what the source returned that day. Permissive ingest preserves the regression in bronze; staging tests catch it; we have evidence to report upstream.

2. **Validation in bronze couples the pipeline to a moving target.** [[idealista]]'s RE API has 28-30 fields per listing today — but PT-specific tweaks happen quarterly. A Pydantic schema in the dlt resource means every upstream field-rename forces a code change before the next run. Validation belongs at the staging layer where dbt models are anyway being maintained per-source.

3. **Single source of truth for "what was published when."** Bronze is the audit trail. If silver/gold ever produce numbers we can't explain, we want to be able to ask "what did the source actually say on date X?" — and have an answer that wasn't filtered through our preconceptions.

## How

**Schema contract** (the only enforcement bronze does):

```python
SCHEMA_CONTRACT = {"data_type": "freeze", "columns": "evolve"}
```

- `data_type=freeze`: type drift on a known column (price was bigint, now string) → load fails loudly. We catch type regressions the same week, but a single new field doesn't break us.
- `columns=evolve`: new fields land silently as NULL. Staging models must be updated to project them, but the bronze load proceeds.

**Where validation DOES belong**:

- **Pipeline configs** (`*_config.py`): YES, Pydantic. These are project-internal contracts ([[pydantic-not-in-dlt]] explains the asymmetry).
- **Bronze ingest**: NO Pydantic, NO validation beyond schema-contract.
- **dbt staging** (`stg_*.sql`): YES — type casts, NULL handling, business-rule checks (`dbt-utils` tests).
- **dbt silver/gold**: YES — referential integrity, cross-source consistency, business KPIs.

**Never-delete invariant**: bronze is append-only at the SCD2 level (versions accumulate; old versions are never removed). Heartbeats UPSERT but never DELETE. The wiki's [[2026-05-08-idealista-enrichment-architecture]] decision describes how Phase 5 enrichment writes go to **silver, not bronze** — the same rule applied to LLM output.

**Per-source schema layout**: each source has its own bronze schema (`bronze_listings`, `bronze_regulatory`, `bronze_geology`, etc. — see warehouse/init/001_create_schemas.sql). Cross-source contamination is impossible at the SQL level. See [[medallion-layering]] for the full schema map.

## See also

- [[pydantic-not-in-dlt]] — the strict corollary on where Pydantic IS and ISN'T allowed
- [[scd2-row-hash]] — the row-hash policy that operates within bronze-permissive constraints
- [[heartbeat-sidecar]] — the staleness signal (because we never delete from bronze)
- [[medallion-layering]] — the broader bronze/silver/gold framing
- [[idealista]], [[jll]], [[remax]], [[zome]] — every dlt-based portal pipeline implements this
