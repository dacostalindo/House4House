---
title: Idealista — three-stream coexistence + Phase 5 enrichment lands in silver
type: decision
last_verified: 2026-05-08
tags: [idealista, pydantic-ai, enrichment, scd2, architecture]
confidence: medium
---

## For future Claude

This is a decision record about the [[idealista]] architecture: three coexisting streams (legacy resale, new dlt-based developments+units, plots), the planned Sprint 4.5 retirement of the legacy `raw_idealista` table, and the rule that Phase 5 LLM-driven description enrichment writes to silver, not bronze. Read this when adding a new idealista entity, considering changing where Pydantic AI output lands, or scoping the legacy-table retirement gate.

## Decision

Three coexisting [[idealista]] streams in bronze:

1. **Legacy `raw_idealista`** — resale catalog via ZenRows Real Estate API discovery + detail. Slated for retirement.
2. **New dlt-driven developments + units** — `idealista_developments` + `idealista_development_units` (SCD2) + heartbeat sidecars (UPSERT). Ships now. Field names match `raw_idealista` verbatim to enable drop-in silver replacement.
3. **Plots** — separate stream (no RE API equivalent for `/comprar-empreendimentos/plots`).

Retirement gate for `raw_idealista`: Sprint 4.5, contingent on a `unified_listings` canonical silver model landing AND hand-labeled-sample precision ≥ 0.9 against the new dlt stream.

Phase 5 enrichment scope (planned, not yet shipped): `ListingEnrichment` Pydantic AI schema parses [[idealista]] descriptions into structured fields (construction year, condition, energy certificate references, etc.). **Output writes to silver, not bronze.** Bronze remains [[bronze-permissive]]; LLM output is downstream.

## Why

**Why three coexisting streams (instead of immediate cutover):**

- The legacy `raw_idealista` is producing usable silver data today. Cutting over before the new stream's quality has been validated against held-out samples would risk a regression visible in production analytics.
- The dlt-based stream uses RE API verbatim names matching `raw_idealista`'s shape — explicit drop-in compatibility. The retirement is engineered to be a "rename the source; everything else works" operation.
- Plots have no RE API equivalent (per [[zenrows-universal-vs-re-api]]); they NEED their own stream regardless.

**Why Phase 5 enrichment writes to silver:**

- [[bronze-permissive]] forbids any judgment-laden writes to bronze, including LLM-derived structured fields. Bronze is the source-faithful audit trail.
- Silver is where conformed, cleaned, validated data lands. LLM output IS validated (Pydantic AI strict-mode parsing into `ListingEnrichment`); the schema check happens at write time. That's silver-shaped, not bronze-shaped.
- Re-running enrichment is idempotent and cheap (description-hash cache); writing to silver lets us re-enrich without polluting the bronze SCD2 history.

**Why hand-labeled-sample precision as the retirement gate:**

- A pure feature-count match between old and new streams would catch volume regressions but miss field-quality regressions (e.g., new stream silently dropping the description body 5% of the time). Hand labels detect that.
- 0.9 threshold is conservative — gives 10% headroom for residual ambiguity without blocking the cutover indefinitely.

## Options considered

1. **Three coexisting streams + Sprint 4.5 retirement gate** (chosen).
2. **Immediate cutover from legacy to dlt-based** (rejected) — too much regression risk; no held-out validation.
3. **Run streams permanently in parallel** (rejected) — pays double-storage forever; complicates silver `unified_listings` semantics.
4. **Phase 5 enrichment writes to bronze** (rejected) — violates [[bronze-permissive]]. Even Pydantic-validated LLM output is judgment, not source-faithful capture.
5. **Phase 5 enrichment writes to a separate `bronze_enrichment` schema** (rejected) — distinguishing two bronze schemas with different policies creates confusion. Silver is unambiguously the right tier for derived data.
6. **Phase 5 enrichment writes to gold** (rejected) — premature aggregation; silver-level structured fields feed multiple gold use cases (search, valuation, comparables).

## Consequences

- Sprint 4.5 will have a focused `unified_listings` silver-modelling sub-task plus the precision-validation work. Retirement is one PR away once both gates pass.
- Phase 5 will land a `silver_properties.listing_enrichments` table joinable to `unified_listings` on listing_id + description_hash. Re-runs are idempotent (cache key = description_hash).
- A description-hash cache (`(listing_id, sha256(description))`) is part of the Phase 5 design; without it, re-runs would re-spend on unchanged descriptions.
- A dead-letter table captures Pydantic AI parse failures (descriptions where the LLM produced output that didn't validate against `ListingEnrichment`) for human review.
- Dual-storage cost stays bounded: both [[idealista]] streams target the same concelhos, refreshing daily. Storage = ~2× a single stream until retirement, ~1× after.

## Status

`accepted` for the three-stream coexistence (Phase 3 PR 1 shipped with all three streams). `accepted` for the silver-not-bronze enrichment placement. Phase 5 implementation hasn't started; the Pydantic AI architectural decision is locked but not battle-tested yet.

`confidence: medium` because Phase 5 is unbuilt — the enrichment-quality + cost behavior under real load may surface refinements (different chunking, a smaller model fine-tuned on PT real-estate prose, etc.). The architectural shape (silver write target, schema, dead-letter) is the load-bearing claim and is not expected to change; quality-tuning is a separate axis.

## See also

- [[idealista]] — the source page documenting all three streams in detail
- [[zenrows-universal-vs-re-api]] — the API-mix that necessitates Universal Scraper for developments
- [[payload-cache-lifecycle]] — the cache making the three-pass scrape economically feasible
- [[scd2-row-hash]] — the row-versioning policy applied to the new dlt streams
- [[heartbeat-sidecar]] — the staleness signal for stub-shaped RE API responses
- [[bronze-permissive]] — the policy forcing Phase 5 enrichment to silver, not bronze
- [[pydantic-not-in-dlt]] — bronze-side Pydantic guardrail (Phase 5 enrichment uses Pydantic AI but only at silver-write time)
