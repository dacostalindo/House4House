# ADR 007 — `BronzeTableConfig` declarative pattern vs hand-rolled bronze DAGs

**Status:** Stub — body TBD (Sprint 9 backfill)
**Decision-makers:** TBD
**Date:** TBD

## Context (TBD)

Some pipelines use the declarative `BronzeTableConfig` pattern (~3-line DAG wrapper that consumes a config dataclass): SCE, RE/MAX (legacy non-dlt path), Zome (legacy non-dlt path). Others have custom hand-rolled bronze DAGs of 100–400 lines: Eurostat, BPStat, ECB, INE, Idealista (legacy raw_idealista path).

When does each approach win? Why isn't there a single consistent pattern?

## Decision (TBD)

`BronzeTableConfig` is the **default** pattern for new bronze loads (declarative; cheap to add new sources). Hand-rolled DAGs are kept where the source has irregular needs:

- Multi-pass ingestion that doesn't fit the JSONL→bronze flow.
- Custom rate-limiting / retry semantics.
- Source-specific validation gates (e.g., Idealista's enrichment thresholds).

## Rejected alternatives (TBD)

- All hand-rolled (no template). Repetition; copy-paste drift.
- All `BronzeTableConfig` (no escape hatch). Forces complex sources into a Procrustean bed.

## Consequences (TBD)

- Two patterns to learn for new contributors.
- Sprint 9 task to refactor the hand-rolled DAGs to `BronzeTableConfig` where possible (Eurostat, BPStat, ECB, INE — Idealista may keep custom due to complexity).
- The dlt-based portal pipelines (RE/MAX, Idealista, Zome) sit outside both patterns — they use dlt's own resource framework. See ADR 003.

## References to dig into when filling

- `pipelines/scraping/template/scraping_bronze_template.py` — the `BronzeTableConfig` dataclass.
- `pipelines/scraping/sce/sce_config.py` — canonical declarative example.
- `pipelines/api/eurostat/eurostat_bronze_dag.py` — hand-rolled example (414 lines).
- Backlog item: "Refactor API pipeline configs for consistency" in Sprint 9 backlog.
