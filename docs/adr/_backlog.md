# ADR Backlog

Architectural decisions that **were made implicitly** during the project's history but never written down. Stubs created in Sprint 4.4 (Workstream E.4); bodies filled during Sprint 9 production-hardening backfill.

**Convention:** ADR files are numbered sequentially. Stubs use the same template as written ADRs but mark `Status: Stub — body TBD`. Don't merge a stub-only PR; bodies must be filled before the ADR is considered "Accepted."

| # | Title | Status | Owner | Sprint |
|---|---|---|---|---|
| 001 | `pipelines/portals/` namespace + dbt-sources-as-canonical column docs | Accepted | Sprint 4.4 prep | S4.4 |
| 002 | MinIO + PostGIS storage split | Stub | TBD | S9 |
| 003 | dlt for the three portal pipelines | Stub | TBD | S9 |
| 004 | Medallion architecture (bronze/silver/gold) | Stub | TBD | S9 |
| 005 | JSONB sidecar columns vs full normalization | Stub | TBD | S9 |
| 006 | SCD2 row_hash exclusion policy | Stub | TBD | S9 |
| 007 | `BronzeTableConfig` declarative pattern vs hand-rolled | Stub | TBD | S9 |

## When to add a new ADR

A decision belongs in an ADR when **all** of the following are true:

1. It's architectural (affects how multiple components interact, not a single function's implementation).
2. It's contested (alternatives existed and were rejected for non-obvious reasons).
3. A future engineer wouldn't be able to derive the rationale by reading the code alone.

Routine implementation choices (variable names, library versions, formatting) don't need ADRs.

## Template

When filling a stub or writing a new ADR, follow ADR 001's structure:

```markdown
# ADR NNN — <one-line decision title>

**Status:** Accepted | Superseded by ADR NNN | Deprecated
**Decision-makers:** <sprint or names>
**Date:** <YYYY-MM-DD>

## Context
What problem prompted the decision; what was the state of the world before.

## Decision
The chosen approach. State as a directive: "We use X for Y."

## Rejected alternatives
Each alternative considered, with one-line rationale for rejection.

## Consequences
What this enables, what it constrains, what new work it creates.

## References
Code paths, related ADRs, Sprint backlog entries.
```

## Filling stubs (Sprint 9 work)

Each stub points at the relevant code paths so the body-fill is straightforward — read those paths, document what's there, document what alternatives existed, document why the current choice won.

Don't over-engineer the backfill. A 200-line ADR for a decision that has held up for a year is fine. The point is to make the rationale recoverable, not exhaustive.
