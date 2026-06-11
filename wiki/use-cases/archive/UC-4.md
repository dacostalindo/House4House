---
title: UC-4 — Qualitative Signal Layer (ARCHIVED)
type: plan
last_verified: 2026-06-11
tags: [use-case, archived, qualitative-signal, news, project-actors, regulatory]
status: archived
---

# UC-4 — Qualitative Signal Layer (ARCHIVED 2026-06-11)

## For future Claude

This is the **archive marker** for UC-4 — the "Qualitative Signal Layer (Agentic News / Project Actors / Regulatory Events)" use-case that was planned on 2026-05-29 but never implemented. UC-4 existed only as the index.md bullet + the log entry; no problem-statement, project-plan, or sprint-plan file was ever created. It was archived 2026-06-11 because its three-track scope was decomposed into two active successors that fit existing structures better. Read this page when (a) you encounter a stale `[[UC-4]]` link in older sprint or concept pages and need to know where the scope actually went, or (b) you're scoping new work that touches news/regulatory/developer-entity signal and want to confirm it isn't already in flight.

## What it was

A single use-case bundling three qualitative-signal tracks for the warehouse:

1. **Articles** — PT real-estate press ingest, LLM-summarized, geo-grounded.
2. **Project Actors** — developer + architect entity enrichment via LLM web-search, FK'd to `dev_uid`.
3. **Regulatory Events** — DRE + municipal PDM events tagged to freguesia.

Originally planned at `sprint-04.7` between [[sprint-04.5]] dedup and [[sprint-05]] hedonic; 6 PRs over ~10 weeks. Introduced "Flow G" (LLM-mediated typed extraction) as a new ingest-flow type. Absorbed an earlier `planning/PoCs/agentic-pipeline` PoC.

## Why archived

By 2026-06-11 the three tracks had natural homes that fit project structures better than a single use-case folder:

- **Articles + Regulatory Events** got their own preflight-grounded PoC in [[planning/PoCs/news-pipeline/design]] (4 sources verified, PTdata API integration locked, daily Sonnet synthesis instead of the embed/cluster stack UC-4 had assumed). The news PoC sprint plan ([[planning/PoCs/news-pipeline/sprint-plan]]) covers both tracks in 5 PRs.
- **Project Actors** is handled by the Knowledge-graph-PoC's silver-layer entity resolver (org-name → NIPC + brand → entity-cluster), where it shares infrastructure with developer-listings work already in flight rather than reinventing it inside a news pipeline.

Keeping UC-4 alive as a parallel framing on top of those two efforts would have created drift: every change to the news PoC or KG-PoC would need a UC-4 doc update, and "Flow G" is just LLM-mediated extraction — a useful pattern, but it lives inside the active PoCs rather than as a use-case-level abstraction.

## Where each track went

| UC-4 track | Active successor | Status |
|---|---|---|
| Articles | [[planning/PoCs/news-pipeline/design]] — PR1 (Idealista) → PR4 (daily Sonnet digest) | Design approved, awaiting sprint slot |
| Regulatory Events (DRE + PDM) | [[planning/PoCs/news-pipeline/design]] — PR5 (DRE via OutSystems screenservices); municipal PDM deferred to PR6+ | DRE preflight-verified; PDM source-by-source post-v1 |
| Project Actors (developer enrichment, LLM web-search) | Knowledge-graph-PoC silver-layer resolver | In flight in a separate workstream; news PoC emits raw NER ORG spans for downstream linkage |

## Architectural artifacts UC-4 shaped that survive

UC-4 never shipped, but during its planning window it was the primary justification for the `dev_uid` stability design that DID ship in [[sprint-04.6]]. Those artifacts remain valid on their own merits — they support **any** future enrichment table that FKs to a stable per-development identifier, not just UC-4's specifically. See:

- [[dev-uid-stability]] — `silver_dev_uid_map` append-only table + `dev_uids[]` array surface.
- [[cross-portal-dev-dedup]] — explains why the volatile `dev_key` lives alongside the stable `dev_uids[]`.

Older mentions of `[[UC-4]]` in those concept pages and in [[sprint-04.6]] have been reframed to point at this archive marker.

## Discarded prior parallel UC-4 work

For completeness: an even earlier "UC-4" design (single-file, dated 2026-05-15, news-driven RE intelligence analyst concept) and its companion `wiki/sprints/sprint-11.md` were removed on 2026-05-29 in favour of the folder-shaped UC-4 framing being archived here. Backups were at `/tmp/uc4-discarded-2026-05-29/` per the 2026-05-29 log entry. Neither version was ever production code.

## See also

- [[planning/PoCs/news-pipeline/design]] — the active successor for Articles + Regulatory Events.
- [[planning/PoCs/news-pipeline/sprint-plan]] — paired PR breakdown.
- [[dev-uid-stability]], [[cross-portal-dev-dedup]] — architectural artifacts shaped by UC-4's planning, still load-bearing.
- 2026-05-29 log entry for the original UC-4 creation; 2026-06-11 log entry for this archive.

## Last verified

2026-06-11 — archived. Never built. Do not resurrect this framing without first reading the design + sprint-plan of the news-pipeline PoC and confirming a genuine gap they don't cover.
