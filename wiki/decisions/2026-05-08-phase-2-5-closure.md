---
title: Phase 2.5 absorbed into Phase 2 (closed, no work to do)
type: decision
last_verified: 2026-05-08
tags: [phase-2, pydantic, scope, decision-history]
confidence: high
---

## For future Claude

This is a decision record about closing Phase 2.5 (post-Phase-2 Pydantic sweep into inline validators). The audit found zero Pydantic-eligible sites; Phase 2.5 had no work to do. Read this when scoping a future "second-pass" phase, considering whether inline-validator code in pipelines is "left over from Phase 2.5" (it isn't), or wondering why the design doc has an "ABSORBED" section.

## Decision

Phase 2.5 — originally scoped as "sweep all 267 inline validators across the codebase to use Pydantic" — is **closed with no work performed**. An audit at Phase 2 close found 90 actual call sites (not 267; the original count was an overestimate) and **zero of them were Pydantic-eligible**. All sites were control-flow guards or external-data validation (where Pydantic is forbidden per [[pydantic-not-in-dlt]]).

The design doc's Phase 2.5 section now reads "ABSORBED BY PHASE 2 (closed 2026-05-08)" with a pointer to this ADR.

## Why

Phase 2 migrated all 4 pipeline configs (`idealista`, `srup`, `crus`, `cadastro`) to Pydantic v2 BaseModel. The ambitious follow-up — "now sweep every other validator-like-call-site" — assumed a long tail of similar opportunities elsewhere.

The audit dispelled that assumption. The 90 actual sites broke down as:

- **Control-flow guards** (~60 sites): defensive `if not value: raise ValueError(...)` patterns inside DAG bodies, scrapers, and transformation steps. These ARE NOT Pydantic candidates — they're conditional logic on locally-computed values, not schema validation.
- **External-data validators** (~25 sites): assertions on values returned from APIs, scraped HTML, or CSV files. These ARE Pydantic-FORBIDDEN per [[pydantic-not-in-dlt]] — bronze must be permissive; validation belongs in dbt staging.
- **Test fixtures** (~5 sites): assertion helpers in `tests/`. Not production code; not in scope.

Phase 2.5 had nothing to do because Phase 2 had already covered the Pydantic-eligible surface (the 4 configs). The remaining 90 sites are correctly NOT Pydantic, and turning them into Pydantic models would create the [[bronze-permissive]] guardrail violation Phase 2 explicitly built around.

## Options considered

1. **Close Phase 2.5 with no work** (chosen) — accept the audit finding; document via this ADR.
2. **Force a sweep anyway** (rejected) — would convert ~25 bronze-side validators into Pydantic, violating [[bronze-permissive]] and [[pydantic-not-in-dlt]]. The exact failure mode the guardrails prevent.
3. **Re-scope Phase 2.5 to "audit-and-document" only** — discarded as duplicating what this ADR already does.
4. **Defer Phase 2.5 indefinitely** (rejected as ambiguous) — open phases create planning debt; close-with-no-work is cleaner.

## Consequences

- The design doc's phase numbering preserves "Phase 2.5" as a section heading, but its contents are this single closure note. Any future contributor reading the design doc sees "ABSORBED BY PHASE 2" and finds this ADR for the rationale.
- The 90 inline-validator sites are NOT future Pydantic candidates. If someone proposes "let's extend Pydantic into the scrapers," the answer is "[[pydantic-not-in-dlt]] — that violation is exactly what Phase 2.5's closure protects against."
- The audit cost (~half day) is the only Phase 2.5 expenditure. Honest accounting: not zero, but small relative to the value of closing the question.
- Future "let's do a sweep" phases need an audit gate first. Lesson learned: an ambitious sweep deserves a 30-minute audit before scoping, not after.

## Status

`accepted` — closed 2026-05-08. Phase 3 PR 1 has shipped on top of this closure. High confidence; the audit data is in the design doc and reproducible.

## See also

- [[pydantic-not-in-dlt]] — the strict guardrail this closure protects
- [[bronze-permissive]] — the broader policy that's the load-bearing reason Phase 2.5 had no work
- [[2026-05-05-uv-workspace-shape]], [[2026-05-05-cosmos-pin]], [[2026-05-08-sqla-1.4-concession]] — the foundational decisions Phase 2 built on top of
