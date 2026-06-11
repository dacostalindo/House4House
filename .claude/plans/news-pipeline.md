# News pipeline — retired pointer

**Status:** retired 2026-06-11.

The authoritative design + implementation plan for the news pipeline now lives in the wiki:

- **Design (authoritative, with full SQL + inlined preflight + failure handling + configs):** [`wiki/planning/PoCs/news-pipeline/design.md`](../../wiki/planning/PoCs/news-pipeline/design.md)
- **Sprint plan (per-PR scope, acceptance, eval gates):** [`wiki/planning/PoCs/news-pipeline/sprint-plan.md`](../../wiki/planning/PoCs/news-pipeline/sprint-plan.md)

This file is preserved as a stub only so existing references in commit messages and prior wiki revisions don't 404. Do not add content here. If you find yourself wanting to edit the news-pipeline plan, edit the wiki design instead — that is the single source of truth.

The v3 content this file previously held (Sonnet-as-corpus-summary architecture, dlt-based bronze, analyst-digest framing) was superseded by the UC-3 reframe locked on 2026-06-11. See the wiki design's "What changed from v3" section for the diff.
