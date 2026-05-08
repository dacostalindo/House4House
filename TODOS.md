# TODOS

## Phase 2.5 — closed (no work to do)

**Status:** absorbed by Phase 2 on 2026-05-08.

The eng-review's "267 inline validators" estimate was a bad-grep artifact. The audit on 2026-05-08 found **zero Pydantic-eligible input-validation sites** in `pipelines/`. The 90 `raise/assert` statements that exist are all control flow, error handling, or external-data shape guards — exactly what the bronze-permissive rule keeps out of Pydantic. Phase 2's typed configs already cover the surface that mattered.

## Consolidate bronze-count anomaly checks into a data-quality helper

**What:** the 15 scattered `if listings_current < N or listings_current > M: alert/raise` patterns across portal DAGs (`remax_dlt_dag.py`, `zome_dlt_dag.py`, etc.) move into either a small Python helper (`pipelines/common/bronze_quality.py` with `assert_bronze_count_in_range(...)`) or dbt singular tests on the bronze tables.

**Why:** the checks are real signal (catches "scrape silently broke and only got 50 listings instead of 5,000"), but the implementation is copy-pasted with slightly different bounds in each DAG. Consolidating gives one place to tune thresholds and one place to find the alert logic.

**Pros:** DRY, easier to review and tune thresholds, opens the door to per-source baseline tracking. Plays naturally with the dbt singular-test pattern (one SQL test per bronze table with hardcoded bounds).

**Cons:** moving the checks out of the DAG hides them from the task-level airflow logs slightly. Mitigated by having the helper raise with a clear error string.

**Context:** discovered during the Phase 2.5 audit (2026-05-08). The 15 sites are exclusively bronze-volume guards — they assert the scrape returned a sane number of rows. Listed sites: see `pipelines/portals/remax/remax_dlt_dag.py:231-248`, `pipelines/portals/zome/zome_dlt_dag.py:258`, plus a few more across portals.

**Depends on:** nothing blocking. Pure refactor. Can also be deferred until the dbt staging tests for portal bronze tables get fleshed out, since dbt singular tests are arguably the better home for these.

---

## Post-autofix idealista verification (Phase 1 final gate)

**What:** trigger `idealista_ingestion_dag` once on the merged main with the autofix sweep applied. Verify the DAG completes green and bronze row counts grow within the same drift envelope as the pre-merge smoke (Δ ~3 developments / ~35 units per run).

**Why:** the eng-review's T1 acceptance gate specified post-autofix idealista smoke before considering Phase 1 fully landed. The pre-merge smoke (commit 8a1646e) covered the .uv migration but predates the ruff autofix (340751b). Closes the gate.

**Context:** ran the dual-stack pre-merge smoke on 2026-05-06 with clean parity. Autofix touched 70 tracked files including some pipeline modules (excluding the 3 with prior WIP). Mechanical fixes only (no UP032 f-string-rewrite landmines triggered, RUF unsafe fixes not enabled), so risk is low — but T1 was explicit about post-autofix verification.

**Depends on:** PR #N merged to main.

---


## Pydantic AI for image_classification_dag.py

**What:** wrap the LLM calls in [pipelines/portals/idealista/image_classification_dag.py](pipelines/portals/idealista/image_classification_dag.py) with Pydantic AI for typed outputs (replacing whatever ad-hoc string parsing currently lives there).

**Why:** typed schema for image-tag silver columns; consistent with the Pydantic AI pattern landed for description enrichment in Phase 5 of the dev-tooling design.

**Context:** Phase 5 of the 2026-05-05 dev-tooling design lands Pydantic AI for *description* enrichment. Image classification is the natural next surface — same shape (LLM input → typed Pydantic output → dlt → silver), different content. Hold until Phase 5 ships and the pattern is exercised once in production.

**Depends on:** Phase 5 of `manuellindo-main-design-20260505-120707.md` (Idealista description enrichment).

---

## Graduate `ty` from advisory to gating CI step

**What:** flip the `continue-on-error: true` flag off in the GitHub Actions workflow added in Phase 4, making `ty check` a hard gate on PRs.

**Why:** type errors should block PRs once tooling is mature, same as `ruff check`. Today ty is in preview and noisy enough that gating would cause more friction than it saves.

**Context:** Phase 6 of the 2026-05-05 dev-tooling design lands ty as advisory. Trigger to graduate is external — Astral declaring ty stable. No deadline. Watch the Astral blog and ty changelog.

**Depends on:** Astral marking ty stable (external trigger, no internal blocker).
