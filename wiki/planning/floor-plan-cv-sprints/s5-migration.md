---
title: S+5 — Wire CV into silver + legacy migration + retire old DAG
type: plan
last_verified: 2026-06-07
tags: [sprint, floor-plan-cv, silver, migration, retirement, legacy]
status: planned
sprint: s5
estimated_effort: 1 week
---

# S+5 — Wire CV into silver + legacy migration + retire old DAG

**Goal:** Connect S+4's bronze CV output into S+1's silver
`unified_listing_spaces`, migrate the 1,473 legacy
`floor_plan_extractions` rows into the new schema as
`cv_floor_plan_v0_legacy`, excise task group B from
`image_classification_dag.py` (task group A keeps running), and archive
the legacy table for a 60-day grace period.

**Depends on:** S+1 (silver skeleton), S+4 (CV bronze rows exist).
**Blocks:** nothing (terminal sprint).

---

## T5.1 — `int_floor_plan_cv_predictions.sql` intermediate model

**What:** dbt intermediate model that unpivots `floor_plan_cv_prediction.payload`
into long format matching `unified_listing_spaces`. Joins through
`floor_plan_blob_ref` to attach each prediction to its listing.

**Files:**
- `dbt/models/intermediate/int_floor_plan_cv_predictions.sql` (new)
- `dbt/models/intermediate/_intermediate__models.yml` (or whichever pattern the repo uses for intermediate model YAMLs)

**Implementation sketch:**
```sql
{{ config(materialized='view') }}

WITH preds AS (
    SELECT
        p.blob_sha256,
        p.model,
        p.prompt_version,
        p.payload,
        p.extracted_at
    FROM {{ source('bronze_listings', 'floor_plan_cv_prediction') }} p
    WHERE p.extraction_status = 'success'
      AND p.payload->>'plan_classification' = 'residential_floor_plan'
),
refs AS (
    SELECT
        r.sha256,
        r.portal,
        r.source_listing_id
    FROM {{ source('bronze_listings', 'floor_plan_blob_ref') }} r
),
floors AS (
    SELECT
        p.blob_sha256,
        p.model,
        p.prompt_version,
        p.extracted_at,
        f.floor_ordinal,
        f.spaces
    FROM preds p,
         jsonb_to_recordset(p.payload->'floors_depicted')
           AS f(floor_ordinal SMALLINT, spaces JSONB)
),
spaces AS (
    SELECT
        f.blob_sha256,
        f.model,
        f.prompt_version,
        f.extracted_at,
        f.floor_ordinal,
        s.observed_raw_label,
        s.space_type,
        s.area_m2,
        s.bbox_pct,
        s.confidence,
        ROW_NUMBER() OVER (
            PARTITION BY f.blob_sha256, s.space_type, f.floor_ordinal
            ORDER BY s.area_m2 DESC
        ) AS ordinal
    FROM floors f,
         jsonb_to_recordset(f.spaces)
           AS s(observed_raw_label TEXT, space_type TEXT,
                area_m2 NUMERIC, bbox_pct JSONB, confidence NUMERIC)
)
SELECT
    r.portal || '|' || r.source_listing_id           AS listing_uid,
    s.space_type,
    s.ordinal,
    s.area_m2,
    'cv_floor_plan_v1'                               AS source,
    s.confidence,
    s.observed_raw_label                             AS space_type_observed_raw,
    s.bbox_pct,
    s.model                                          AS model_version,
    s.blob_sha256                                    AS plan_image_hash,
    s.extracted_at
FROM spaces s
JOIN refs r ON r.sha256 = s.blob_sha256
WHERE s.confidence >= {{ var('cv_confidence_threshold', 0.5) }}
```

The cross-page dedup is delegated to a follow-up step (or accepted as
"per-page rows" — silver consumers can de-dupe). Use `cv_confidence_threshold`
as a dbt var so it's tunable post-T4.7 calibration.

**Acceptance:**
- `dbt run --select int_floor_plan_cv_predictions` succeeds.
- Row count > 0 (assuming S+4 backfill ran).
- `listing_uid` format matches `stg_portal_spaces_zome` (`portal|listing_id`).
- No NULL `area_m2`.

**Depends on:** S+4 (T4.6).

---

## T5.2 — Widen `unified_listing_spaces.sql` to UNION CV predictions

**What:** Expand the silver model from S+1's zome-only pass-through to a
full UNION ALL of zome_native + cv_floor_plan_v1 + (later) cv_floor_plan_v0_legacy.

**Files:**
- `dbt/models/silver/properties/unified_listing_spaces.sql` (modify)
- `dbt/models/silver/properties/_unified_listing_spaces.yml` (modify — relax `space_type` `not_null` to allow NULL for legacy unmapped labels)

**New SQL:**
```sql
{{ config(materialized='table', schema='silver_properties') }}

SELECT * FROM {{ ref('stg_portal_spaces_zome') }}

UNION ALL

SELECT * FROM {{ ref('int_floor_plan_cv_predictions') }}
```

T5.3 will add a third UNION arm for the legacy migration.

**Acceptance:**
- Row count = S+1 row count + new CV row count.
- Per-source breakdown in silver matches expectations
  (zome_native ~4k–6k, cv_floor_plan_v1 ~10k–15k after S+4).
- All existing dbt tests still pass.

**Depends on:** T5.1.

---

## T5.3 — Migrate 1,473 legacy `floor_plan_extractions` rows

**What:** Translate the old idealista-only schema into
`floor_plan_cv_prediction` + the silver model. Per Q13 mapping.

**Files:**
- `pipelines/enrichment/floor_plan_cv/migrate_v0_legacy.py` (new, one-shot)
- `dbt/models/intermediate/int_floor_plan_cv_predictions_v0_legacy.sql` (new) — parallel intermediate model for the legacy source

**Migration script logic:**
1. Read every row in `bronze_listings.floor_plan_extractions`.
2. For each, synthesize a `payload` JSONB matching the v1 schema:
   - `plan_classification = 'residential_floor_plan'`
   - `page_classification_confidence = extraction_confidence` (best proxy)
   - `floors_depicted = [{floor_label, floor_ordinal: 1, spaces: [...]}]`
     - `spaces` = unpack `rooms` JSONB via taxonomy map:
       - For each `room_name` key:
         - `observed_raw_label = strip_trailing_index(room_name)` (`quarto_1` → `quarto`)
         - `space_type = PT_LABEL_TO_SPACE_TYPE.get(observed_raw_label)` (may be NULL for hall/escritorio/arrumos)
         - `area_m2 = value`
         - `area_source = 'annotated_on_plan'` (assumption — the v0 prompt only kept labelled areas)
         - `is_suite = (observed_raw_label == 'suite')`
         - `bbox_pct = null`
         - `confidence = extraction_confidence`
3. INSERT into `floor_plan_cv_prediction` with:
   - `model = 'claude-vision-v0-legacy'` (or extract from `model_used` column)
   - `prompt_version = 0` (sentinel meaning "legacy")
   - `extraction_status = 'success'`
   - `extracted_at = _extracted_at`
   - `blob_sha256` = **lookup** — see caveat below

**Caveat: blob_sha256 for legacy rows.**
The legacy table stores `image_url`, not bytes. To get sha256:
- **Option A** — re-fetch the image URL through `floor_plan_ingest_dag`,
  compute sha256 on the fly, populate blob tables, then migrate. Slower but
  yields full blob lineage.
- **Option B** — fabricate a synthetic sha256 sentinel like
  `legacy_idealista_{property_id}_{image_position}`, skip blob ingestion
  for these rows, accept that they have no MinIO blob.

**Recommend Option A** — the URLs are mostly fresh (S+2 ran recently),
and having blob lineage means CV could be re-run on the v1 path for
direct v0/v1 comparison.

For unmapped legacy labels (`hall`, `escritorio`, `arrumos`), the
`space_type` is NULL but `observed_raw_label` is preserved — so the
data isn't lost.

`int_floor_plan_cv_predictions_v0_legacy.sql` is structurally identical
to T5.1's intermediate but sources from the legacy-model rows (filter by
`model='claude-vision-v0-legacy'`) and emits `source='cv_floor_plan_v0_legacy'`
instead of `cv_floor_plan_v1`.

**Acceptance:**
- 1,473 rows inserted into `floor_plan_cv_prediction` with
  `model='claude-vision-v0-legacy'`.
- All legacy `rooms` JSONB keys preserved in `observed_raw_label`
  (hall/escritorio/arrumos appear with NULL space_type).
- Silver row count grows by the expected delta.
- Unified `unified_listing_spaces.sql` UNIONs all three sources.

**Depends on:** T5.2.

---

## T5.4 — Excise task group B from `image_classification_dag.py`

**What:** Surgically remove the floor-plan-extraction half of the legacy
DAG. Task group A (render/condition/finish) stays. No production traffic
to `bronze_listings.floor_plan_extractions` after this lands.

**Files:**
- `pipelines/portals/idealista/image_classification_dag.py` (modify) —
  delete the `extract_floor_plans` task and its `FLOOR_PLAN_PROMPT`
  constant; keep `CLASSIFICATION_PROMPT` and task group A intact.
- `pipelines/portals/idealista/tests/test_image_classification_dag.py`
  (if exists) — remove tests for the deleted task

**Acceptance:**
- `airflow dags test image_classification_dag <date>` succeeds with
  task group A only.
- Grep confirms `FLOOR_PLAN_PROMPT` no longer referenced anywhere.
- `bronze_listings.floor_plan_extractions` row count stays frozen
  (no new INSERTs) after this lands.

**Depends on:** T5.3 (migration complete first; don't excise the writer
while there's data only it has).

---

## T5.5 — Archive legacy table

**What:** Rename `bronze_listings.floor_plan_extractions` to
`floor_plan_extractions_archived_v0` and revoke INSERT/UPDATE/DELETE
permissions. Table stays readable for 60 days; then a follow-up `DROP TABLE`.

**Files:**
- `pipelines/enrichment/floor_plan_cv/sql/archive_legacy_table.sql` (new)

**SQL:**
```sql
ALTER TABLE bronze_listings.floor_plan_extractions
  RENAME TO floor_plan_extractions_archived_v0;

REVOKE INSERT, UPDATE, DELETE ON bronze_listings.floor_plan_extractions_archived_v0
  FROM warehouse;
GRANT SELECT ON bronze_listings.floor_plan_extractions_archived_v0
  TO warehouse;

COMMENT ON TABLE bronze_listings.floor_plan_extractions_archived_v0 IS
  'Archived 2026-XX-XX. Replaced by bronze_listings.floor_plan_cv_prediction. '
  'Source: pipelines/portals/idealista/image_classification_dag.py task group B '
  '(deleted). Schedule for DROP after 60-day grace period (target: 2026-YY-YY).';
```

**Follow-up reminder:** Add a calendar / task item dated 60 days out:
"DROP TABLE bronze_listings.floor_plan_extractions_archived_v0 if no one
has accessed it." Use the existing TODOS.md convention if there is one.

**Acceptance:**
- Table renamed; old name no longer resolves.
- INSERT to the renamed table fails (permissions revoked).
- SELECT still works.
- Wiki sprint log records the archival date + the 60-day DROP target.

**Depends on:** T5.4.

---

## T5.6 — Wiki updates + decision records

**What:** Final round of wiki maintenance to close out the floor-plan-CV
project.

**Files:**
- `wiki/log.md` — entries for each merged sprint commit (per-commit basis)
- `wiki/sources/idealista.md` — deprecation note: legacy table archived,
  cross-link to new CV pipeline
- `wiki/sources/zome.md` — confirm `areas_extras` ground-truth role is
  documented (S+1 should have done this; double-check)
- `wiki/index.md` — final routing for `pipelines/enrichment/floor_plan_cv/`,
  `pipelines/media/`, `dbt/models/silver/properties/unified_listing_spaces.sql`
- `wiki/decisions/` — decision records for: shape A silver, closed-9
  taxonomy, Path A replacement, OCR-hybrid (or LLM-only per S+3), model
  choice (per S+3 bake-off)
- `wiki/concepts/per-room-areas.md` — concept page (if not done in S+1)
- `wiki/concepts/floor-plan-cv.md` — concept page covering the whole
  pipeline at a high level, cross-linking the planning doc

**Acceptance:**
- `/wiki-lint` passes.
- `/wiki-reconcile` finds no drift.
- Every decision locked in the interview has a corresponding decision
  record in `wiki/decisions/`.

**Depends on:** all above S+5 tasks.

---

## Out of scope for S+5

- The follow-up `DROP TABLE` after 60 days (separate one-off task).
- The deferred "highest-res for image classification (task A) too"
  investigation flagged in the plan doc.
- Any v2 CV improvements (re-running v1 on the same labelled set, self-eval
  second-call, etc.).

## Open questions for S+5

- For the legacy migration: do we re-fetch image URLs via
  `floor_plan_ingest_dag` to get blob lineage (Option A), or accept
  blob-less legacy rows (Option B)? Recommend A; gate on URL availability.
- Cross-page dedup logic in `int_floor_plan_cv_predictions`: should silver
  collapse same-space-different-page predictions, or keep them per-page?
  Default keep-per-page; revisit if downstream consumers complain.
- Should we backfill `metadata.cv_floor_plan_benchmark` for the legacy
  v0 rows? Probably no — different prompt, different model, would
  contaminate the v1 calibration story. Document the decision either way.
