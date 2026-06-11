---
title: Floor-plan CV — per-room area extraction across portals
type: plan
last_verified: 2026-06-07
tags: [plan, cv, vision-llm, floor-plans, zome, idealista, jll, remax, ocr, minio]
status: design-approved
---

# Floor-plan CV — per-room area extraction across portals

## For future Claude

This page is the complete design plan for adding **per-room floor areas** to
silver, validated by Zome's structured `areas_extras` ground-truth and
extended to the other 3 portals via computer vision over their floor-plan
images. Captures every architectural decision from a 13-question interview
on 2026-06-07.

Read this when:
- You're about to start any sprint touching floor plans, room-level areas,
  vision-LLM extraction, or the `unified_listing_spaces` silver model.
- You're considering changes to `pipelines/portals/idealista/image_classification_dag.py`
  — the floor-plan-extraction half (task group B) is being **replaced** per
  Path A below; image classification (task group A) is **untouched**.
- You're picking up mid-sprint and need to know which decisions were
  already locked vs. still TBD.
- You're sizing a new experiment that depends on per-room area data
  (e.g. listing-similarity, layout classification, m²-per-bedroom analytics).

## Project goal

Three ranked sub-goals, in build order:

1. **Surface** Zome's existing per-room area data (`areas_extras` JSONB) into
   a queryable silver model. **Prerequisite for everything else.** Pure SQL,
   no ML, immediate analytical value (1,447 listings labelled).
2. **Archive** floor-plan images into MinIO with content-hash dedup. Enabler
   for (3) — local bytes, URL-rot-proof, reproducible inputs.
3. **Extract** per-room areas from the other 3 portals' floor plans (and
   from the ~5,604 Zome listings that have plans but empty `areas_extras`)
   via vision-LLM + OCR-hybrid. Zome's 1,230 plans-with-areas listings
   serve as the labelled benchmark.

## What's already in production (and what we're replacing)

| Lives at | What it does | Status |
|---|---|---|
| `pipelines/portals/idealista/image_classification_dag.py` task group **A** (render/condition/finish) | Photo classification | **Keeps running, untouched.** |
| `pipelines/portals/idealista/image_classification_dag.py` task group **B** (floor plan extraction) | Idealista-only, Aveiro-only, 1,473 rows in `bronze_listings.floor_plan_extractions` | **Replaced** by new portal-agnostic DAGs. Legacy rows migrated to `cv_floor_plan_v0_legacy` source in new schema; old table archived. |
| `pipelines/enrichment/plot_listing_extraction/` | Claude structured-output pattern using plain `anthropic` SDK + Pydantic models. Same DAG + `schema.py` shape we mirror for CV. | **Reference architecture** — copy the pattern, don't invent a new one. |

The legacy pipeline is the **v0** of what we're shipping as **v1**. Same
anatomy, missing the MinIO blob layer, cross-portal generalization, ground
truth, and silver landing.

## Ranked decisions (in interview order)

### Q1 — Per-room data location
`areas_extras` JSONB on `bronze_listings.zome_listings`. 9-key dict per listing:
`rooms, suite, wcs, kitchen, livingRoom, balcony, terrace, garden, garage`.
Each value is an **array of m² strings**. Array length = count of that space
type. Coverage: 8,774/10,628 non-null (82.5%), but only **1,447 actually populated** (13.6%).
The rest are the empty-arrays sentinel. **`rooms` = quartos (non-suite bedrooms);
`suite` = en-suite bedrooms.** A `suite` is a bedroom with a WC inside it.

Sample (zome listing_id=134288):
```json
{"wcs":["3.2","4.9","5.9"],"rooms":["14.3","14.3"],"suite":["18.6"],
 "garage":["38"],"garden":[],"balcony":["15.9","35.8"],"kitchen":["17.6"],
 "terrace":[],"livingRoom":["49"]}
```
→ 3 bathrooms, 2 bedrooms, 1 suite, 1 garage, 2 balconies, 1 kitchen, 1 living room.

### Q3 — Goal ranking
**(3) Surface → (2) Archive → (1) CV.** Confirmed.

### Q4 — Silver schema shape
**Shape A — long/EAV.** One row per `(listing_uid, space_type, ordinal, source)`.
Wide table would force NULLs for the 87% of listings without per-space data
and can't express per-space provenance cleanly. Long table only stores rows
that exist.

### Q5 — Canonical taxonomy
- **(a) Preserve suite distinction.** Closed-9 enum: `bedroom, bedroom_suite,
  bathroom, kitchen, living_room, balcony, terrace, garden, garage`. Suite
  definition (bedroom with WC inside) is the CV prompt context.
- **(b) English snake_case.** Consistent with silver convention.
- **(c) Closed enum.** Lossy on the CV side — handled by the
  `space_type_observed_raw` insurance column preserving the original label
  before bucketing.

### Q6 — Lineage layout
- **(a) L2.** Portal-native staging exists only for portals that natively
  expose per-room data → today, only `stg_portal_spaces_zome.sql`. No stub
  files for idealista/jll/remax. CV output gets its own intermediate model
  (`int_cv_floor_plan_predictions.sql` or similar).
- **(b)** Production CV **never** runs on the 1,230 zome listings that have
  `areas_extras`. Benchmark CV runs on a stratified sample of them — see Q11.
- **(c) Source enum, TEXT not Postgres ENUM:** `zome_native`, `cv_floor_plan_v1`,
  `cv_floor_plan_v0_legacy` (post-migration), `description_nlp_v1` (future),
  `manual` (future).
- **(d) Schema** — see [Silver schema](#silver-schema) below.

### Q9 — Multi-variant blob model
Three roles per plan: `pdf_source` (raw bytes from JLL/RE/MAX PDFs),
`image_full` (CV input — full-quality WebP-lossless for PDFs, native JPG for
Zome/Idealista), `image_preview` (UI display — WebP-lossy q80, 1024 px long side).

- **Bucket**: `s3://raw/floor-plans/by-hash/{sha[:2]}/{sha[2:4]}/{sha}.{ext}`
  (nested under existing `raw` bucket, content-addressed, two-level shard).
- **PDF rasterization**: WebP-lossless at **3000 px long side** (~300 DPI for
  A3, plenty for vision models). Uniform CV input format across all 4 portals.
- **CV uses highest available resolution; preview is downsampled for UI verification.**
  Open investigation: same principle should be evaluated for image
  classification (task group A in the legacy DAG) — possible quality
  improvement, but out of scope for v1.

### Q10 — Inference model & granularity
- **(a) Per-blob, sha256-cached.** One CV call per unique `image_full`. Same
  plan reused across 5 listings of a development = 1 CV call, not 5. Silver
  does deterministic post-aggregation across (listing → blob → cv_prediction).
- **(b) Hybrid OCR + vision-LLM**, gated on E1 (OCR yield sampling). If
  PaddleOCR-PT extracts clean `(label, area)` pairs on ≥60% of sampled plans,
  OCR-first hybrid ships. Otherwise vision-LLM-only.
- **(c) Bake-off (E2): Claude Sonnet 4.5 vs Gemini 2.5 Pro.** Same 100-blob
  stratified sample, identical prompts, identical structured-output schema.
  Picked on cost unless quality gap on MAE >15%.
- **(d) Airflow DAGs:** `floor_plan_ingest_dag` (downloads + rasterizes +
  writes blob tables) → `floor_plan_cv_dag` (OCR + vision-LLM + writes
  prediction table). Triggered after each portal's bronze refresh.

### Q11 — Output schema & prompt design
- **Confidence-threshold-for-omission = 0.5 in v1.** Calibrate against the
  1,230 benchmark set during E2 — final number is data-driven, not a priori.
- **Pydantic + raw `anthropic` SDK.** No `pydantic-ai`. Mirror the pattern
  in `pipelines/enrichment/plot_listing_extraction/schema.py` exactly.
- **Bucketing in post-process (Python lookup table), not in-prompt.** Model
  emits `observed_raw_label` + `is_suite`; Python maps to `space_type`. Easier
  to evolve than prompts.

### Q12 — Pivot path
**Path A — Replace.** Build new pipeline per design; migrate the 1,473
legacy rows as `cv_floor_plan_v0_legacy` source; deprecate then archive
`bronze_listings.floor_plan_extractions` after a 60-day grace period.

### Q13 — Migration mapping
The 10 legacy PT keys → 9 EN enum + 3 unmapped:

| Legacy key | v1 `space_type` | v1 `observed_raw_label` |
|---|---|---|
| `suite` | `bedroom_suite` | `suite` |
| `quarto` | `bedroom` | `quarto` |
| `sala` | `living_room` | `sala` |
| `cozinha` | `kitchen` | `cozinha` |
| `wc` | `bathroom` | `wc` |
| `varanda` | `balcony` | `varanda` |
| `garagem` | `garage` | `garagem` |
| `hall` | **NULL** | `hall` |
| `escritorio` | **NULL** | `escritorio` |
| `arrumos` | **NULL** | `arrumos` |

`hall/escritorio/arrumos` rows preserved as evidence (raw label kept) but not
bucketed — invisible to space-typed queries, retrievable via raw label.

## Silver schema

```sql
silver.unified_listing_spaces
─────────────────────────────────────────────────────────────────────
listing_uid              TEXT       NOT NULL
space_type               TEXT       NULL      -- 9-enum; NULL for unmapped legacy labels
ordinal                  SMALLINT   NOT NULL  -- 1..N within (listing_uid, space_type, source)
area_m2                  NUMERIC    NOT NULL
source                   TEXT       NOT NULL  -- zome_native | cv_floor_plan_v1 | cv_floor_plan_v0_legacy | ...
confidence               NUMERIC    NULL      -- [0,1], NULL for zome_native
space_type_observed_raw  TEXT       NULL      -- pre-bucket CV label / legacy PT key
bbox_pct                 JSONB      NULL      -- {"x":,"y":,"w":,"h":,"page":}; normalized 0–1
model_version            TEXT       NULL      -- 'claude-sonnet-4-5' | 'gemini-2.5-pro' | ...
plan_image_hash          TEXT       NULL      -- SHA256 of source image_full blob
extracted_at             TIMESTAMP  NOT NULL
PRIMARY KEY (listing_uid, space_type, ordinal, source)
```

Note: `space_type` is **NULL** for unmapped legacy categories (`hall`, etc.).
Adjust PK accordingly — Postgres treats NULLs as distinct in unique
constraints, so the legacy rows don't collide.

Staging models that feed it:
- `dbt/models/staging/portals/stg_portal_spaces_zome.sql` — unpivots
  `areas_extras` JSON via `jsonb_each` + `jsonb_array_elements` →
  rows with `source='zome_native'`.
- `dbt/models/intermediate/int_floor_plan_cv_predictions.sql` — joins
  `bronze.floor_plan_cv_prediction` + `bronze.floor_plan_blob_ref` →
  rows with `source IN ('cv_floor_plan_v1','cv_floor_plan_v0_legacy')`.
- `unified_listing_spaces.sql` = `UNION ALL` of the two.

## Bronze schemas

### Blob layer (MinIO + Postgres metadata)

```sql
bronze_listings.floor_plan_blob
─────────────────────────────────────────────────
sha256              TEXT PRIMARY KEY
role                TEXT NOT NULL              -- pdf_source | image_full | image_preview
mime_type           TEXT NOT NULL              -- application/pdf | image/jpeg | image/webp
storage_uri         TEXT NOT NULL              -- s3://raw/floor-plans/by-hash/...
bytes_size          INTEGER NOT NULL
width_px            INTEGER NULL               -- NULL for pdf_source
height_px           INTEGER NULL               -- NULL for pdf_source
page_index          SMALLINT NULL              -- NULL for pdf_source; 1-based for image_*
derived_from_sha256 TEXT NULL REFERENCES floor_plan_blob(sha256)
first_seen_at       TIMESTAMP NOT NULL
CHECK (role IN ('pdf_source','image_full','image_preview'))
CHECK (role <> 'pdf_source' OR (page_index IS NULL AND derived_from_sha256 IS NULL))
CHECK (role <> 'image_preview' OR derived_from_sha256 IS NOT NULL)
```

```sql
bronze_listings.floor_plan_blob_ref
─────────────────────────────────────────────────
portal             TEXT NOT NULL                -- zome | idealista | jll | remax
source_listing_id  TEXT NOT NULL
ordinal            SMALLINT NOT NULL            -- 1..N within the listing's plan array
sha256             TEXT NOT NULL REFERENCES floor_plan_blob(sha256)
                                                -- points at the image_full row
source_url         TEXT NOT NULL                -- original URL we downloaded from
fetched_at         TIMESTAMP NOT NULL
PRIMARY KEY (portal, source_listing_id, ordinal)
```

### CV prediction table

```sql
bronze_listings.floor_plan_cv_prediction
─────────────────────────────────────────────────
blob_sha256         TEXT NOT NULL REFERENCES floor_plan_blob(sha256)
model               TEXT NOT NULL               -- 'claude-sonnet-4-5' | 'gemini-2.5-pro' | 'paddleocr-pt-v1'
prompt_version      SMALLINT NOT NULL
payload             JSONB NOT NULL              -- the full structured output, verbatim
extraction_status   TEXT NOT NULL               -- success | refused | schema_error | http_error
error_message       TEXT NULL
extracted_at        TIMESTAMP NOT NULL
PRIMARY KEY (blob_sha256, model, prompt_version)
```

One row per (blob, model, prompt_version). `int_floor_plan_cv_predictions`
unpivots `payload.floors_depicted[].spaces[]` into long format for silver.

### Benchmark table

```sql
metadata.cv_floor_plan_benchmark
─────────────────────────────────────────────────
run_id              TEXT NOT NULL                -- e.g. 'sonnet-4-5_2026-06-08'
listing_uid         TEXT NOT NULL                -- always a zome listing in the 1,230 set
blob_sha256         TEXT NOT NULL
space_type          TEXT NOT NULL
ordinal             SMALLINT NOT NULL
area_m2_true        NUMERIC NOT NULL             -- from areas_extras
area_m2_pred        NUMERIC NULL                 -- NULL = model missed
error_m2            NUMERIC NULL
confidence_pred     NUMERIC NULL
model               TEXT NOT NULL
prompt_version      SMALLINT NOT NULL
run_at              TIMESTAMP NOT NULL
PRIMARY KEY (run_id, listing_uid, space_type, ordinal)
```

## CV output payload schema (`payload` JSONB)

```json
{
  "plan_classification": "residential_floor_plan",
  "page_classification_confidence": 0.95,
  "floors_depicted": [
    {
      "floor_label": "Piso 0",
      "floor_ordinal": 1,
      "spaces": [
        {
          "observed_raw_label": "Sala",
          "space_type": "living_room",
          "area_m2": 22.0,
          "area_source": "annotated_on_plan",
          "is_suite": false,
          "bbox_pct": {"x":0.42,"y":0.18,"w":0.21,"h":0.15},
          "confidence": 0.92
        }
      ]
    }
  ],
  "refusal_reason": null
}
```

`plan_classification` values: `residential_floor_plan | site_plan |
section_diagram | elevation | exterior_photo | not_a_plan | ambiguous`.
Non-`residential_floor_plan` rows: silver drops them (empty `floors_depicted`).

`area_source`: `annotated_on_plan | inferred_from_scale | refused`. Only
`annotated_on_plan` predictions sit in the high-confidence band by default.

## Prompt structure (6 fixed sections)

1. **Role.** "You extract per-room floor areas from Portuguese real-estate floor plans."
2. **Output contract.** "Call the `report_floor_plan` tool. Do not respond in prose."
3. **Plan classification.** "If the image is not a residential floor plan
   (site plan, elevation, photo, brochure page), set `plan_classification`
   accordingly and return `floors_depicted: []`. Do not invent rooms."
4. **Suite definition (verbatim).** "`bedroom_suite` = a bedroom with a
   bathroom located inside it. If you cannot trace a door from the bedroom
   into a private WC, the bedroom is `bedroom`."
5. **Area extraction policy.** "Prefer areas annotated on the plan as text
   (e.g. 'Sala 22 m²'). Set `area_source: annotated_on_plan`. If areas aren't
   annotated, you may estimate by scale bar / dimension lines and set
   `area_source: inferred_from_scale`. If you can't do either with confidence
   ≥ 0.5, omit the space entirely — do not invent."
6. **Multi-floor.** "If the image depicts multiple floors (e.g. ground floor +
   first floor side-by-side), produce one `floors_depicted` entry per floor
   in reading order."

Bucketing taxonomy (PT label → 9-enum) lives in a Python lookup table at
`pipelines/enrichment/floor_plan_cv/taxonomy.py`. Unknown labels:
`space_type=NULL`, `observed_raw_label` preserved, surfaced via a metadata
report each run.

## Experiments (pre-build, gates architecture)

### E1 — OCR yield sampling
- Run PaddleOCR (PT lang pack) on 100 stratified `image_full` blobs.
- Measure: % of plans where ≥1 clean `(room_label, area_m2)` pair extracts;
  % where ≥50% of expected spaces extract.
- **Decision criterion**: if yield ≥60%, ship OCR-first hybrid. If <30%,
  vision-LLM-only.
- Output to `metadata.cv_floor_plan_experiment` keyed by
  `(experiment_id='e1', blob_sha256, model='paddleocr-pt-v1')`.

### E2 — Vision-LLM bake-off
- Same 100-blob sample (intersected with the 1,230-listing labelled set so
  ground truth exists).
- Sonnet 4.5 vs Gemini 2.5 Pro, identical prompts + structured output schema.
- Metrics: per-space MAE on area, count F1, suite/bedroom confusion, refusal
  rate, cost per call.
- **Decision criterion**: cheaper unless quality gap on MAE >15%.
- Output to same `metadata.cv_floor_plan_experiment` table.

Both experiments are disposable — not silver, not gold, not consumed by
analytics.

## DAG topology

```
existing portal DAGs (bronze refresh)
        │
        ▼
floor_plan_ingest_dag  ───── reads floor_plan_urls across 4 portal-listings tables
        │                    downloads new (unseen-hash) URLs from CDN
        │                    rasterizes PDFs → WebP-lossless 3000px
        │                    generates WebP-lossy q80 1024px preview
        │                    uploads to s3://raw/floor-plans/by-hash/
        │                    writes floor_plan_blob + floor_plan_blob_ref
        ▼
floor_plan_cv_dag      ───── reads image_full blobs not yet scored at
                             current prompt_version × model
                             [hybrid path] PaddleOCR pass first
                             [hybrid path] vision-LLM fallback on misses
                             writes floor_plan_cv_prediction
                             writes failures with extraction_status
        │
        ▼
dbt build              ───── stg_portal_spaces_zome
                             int_floor_plan_cv_predictions
                             unified_listing_spaces (UNION of native + CV)
```

Excluded from production CV (Q6.b): the 1,230 zome listings whose
`areas_extras` is populated. They feed silver as `zome_native` only.

## Retirement sequence (Path A)

1. Ship new schema (silver `unified_listing_spaces` empty + bronze
   `floor_plan_blob`, `floor_plan_blob_ref`, `floor_plan_cv_prediction`,
   `metadata.cv_floor_plan_benchmark`).
2. Ship MinIO blob layer + `floor_plan_ingest_dag`; backfill blobs for all 4 portals.
3. Run E1 + E2; lock OCR-vs-LLM architecture; lock model.
4. Ship `floor_plan_cv_dag`; backfill production CV (excluding the 1,230 listings).
5. Wire `stg_portal_spaces_zome` + `int_floor_plan_cv_predictions` into
   `unified_listing_spaces`. Verify silver populates correctly.
6. Migrate 1,473 legacy rows from `bronze_listings.floor_plan_extractions`
   into `floor_plan_cv_prediction` with `model='claude-vision-v0-legacy'`,
   `source='cv_floor_plan_v0_legacy'`. Mapping per Q13.
7. Excise task group B from `pipelines/portals/idealista/image_classification_dag.py`
   (task group A — render/condition/finish — keeps running).
8. `RENAME TABLE bronze_listings.floor_plan_extractions TO floor_plan_extractions_archived_v0`;
   revoke writes; keep readable.
9. 60-day grace period; then `DROP TABLE` once nothing references it.

## Sprint sizing (estimated)

| Sprint | Scope | Effort |
|---|---|---|
| **S+1** | Branch (3) surface: `stg_portal_spaces_zome` + `unified_listing_spaces` skeleton (zome_native only). Schema YAMLs + wiki updates. | ~1 week |
| **S+2** | Branch (2) archive: MinIO bucket setup, `floor_plan_blob` + `floor_plan_blob_ref`, `floor_plan_ingest_dag` with PDF rasterization, full backfill. | ~1.5 weeks |
| **S+3** | Experiments E1 + E2; pick OCR-vs-LLM architecture + model. | ~3 days |
| **S+4** | Branch (1) CV: `floor_plan_cv_prediction` table, taxonomy module, `floor_plan_cv_dag`, production backfill (excluding 1,230 labelled). | ~1.5 weeks |
| **S+5** | Wire CV into silver; legacy migration; image_classification_dag refactor; archive old table. | ~1 week |

Total: ~5–6 weeks calendar. Each sprint independently shippable; (3) and (2)
deliver value before (1) ships.

## Open decisions (deferred, not blockers)

| Item | When to decide | Notes |
|---|---|---|
| Production confidence threshold for omission | During E2 calibration | v1 default 0.5; tune from confidence-vs-accuracy curve on 1,230 set. |
| Image classification (DAG task A) resolution policy | Post-v1, separate investigation | User asked: same "use highest-res for inference, store lowest-res" principle applied to floor-plan CV may also benefit photo classification. Out of scope for this plan; flagged for follow-up. |
| Surrogate `space_id BIGSERIAL` PK vs natural 4-col PK | If/when another table FKs into `unified_listing_spaces` | Currently natural PK; switch trivially via add-column + UNIQUE migration. |
| `description_nlp_v1` source | Future sprint | Mining `descricao_completa` for area mentions; complementary signal to vision. |
| Manual override workflow | When the first analyst wants to correct a row | `source='manual'` already in the enum. |

## Wiki cross-refs to update on landing

Per project CLAUDE.md rules ("after every commit, update the wiki"):

- [`wiki/log.md`](../../../log.md) — one-line entries per merged sprint.
- [`wiki/sources/zome.md`](../../../sources/zome.md) — add note: `areas_extras`
  is the ground-truth anchor for floor-plan CV (cross-link this page).
- [`wiki/sources/idealista.md`](../../../sources/idealista.md) — legacy
  `floor_plan_extractions` deprecation note.
- [`wiki/index.md`](../../../index.md) §"By area of code" — add
  `pipelines/enrichment/floor_plan_cv/` and `dbt/models/silver/properties/unified_listing_spaces.sql`
  rows.
- New concept pages (optional but recommended):
  `wiki/concepts/per-room-areas.md` and
  `wiki/concepts/floor-plan-cv.md`.
- New decision records (one per major fork resolved here): silver shape A,
  closed-9 taxonomy, Path A replacement, OCR-hybrid gating, Sonnet/Gemini bake-off.

## Files to create / modify

**New (pipelines):**
- `pipelines/enrichment/floor_plan_cv/__init__.py`
- `pipelines/enrichment/floor_plan_cv/schema.py` (Pydantic; mirror `plot_listing_extraction/schema.py`)
- `pipelines/enrichment/floor_plan_cv/taxonomy.py` (PT label → 9-enum lookup)
- `pipelines/enrichment/floor_plan_cv/ocr.py` (PaddleOCR-PT wrapper)
- `pipelines/enrichment/floor_plan_cv/vision_llm.py` (Anthropic + Gemini wrappers)
- `pipelines/enrichment/floor_plan_cv/prompts.py` (6-section prompt template, versioned)
- `pipelines/enrichment/floor_plan_cv_dag.py`
- `pipelines/media/floor_plan_ingest_dag.py` (or `pipelines/enrichment/floor_plan_ingest_dag.py`)
- `pipelines/media/blob_store.py` (MinIO helpers — content-hash addressing, raster ops)

**New (dbt):**
- `dbt/models/staging/portals/stg_portal_spaces_zome.sql`
- `dbt/models/intermediate/int_floor_plan_cv_predictions.sql`
- `dbt/models/silver/properties/unified_listing_spaces.sql`
- `dbt/models/silver/properties/_unified_listing_spaces.yml` (tests + docs)
- Source YAML additions for `floor_plan_blob`, `floor_plan_blob_ref`,
  `floor_plan_cv_prediction` in `_staging_listings__sources.yml`.

**Modified:**
- `dbt/models/staging/listings/_staging_listings__sources.yml`:1063 —
  `areas_extras` description already updated (2026-06-07).
- `pipelines/portals/idealista/image_classification_dag.py` — excise task
  group B (floor plan extraction); keep task group A.
- `docker-compose.yml` — verify `floor-plans` prefix in `raw` bucket
  (no new container needed; reuse existing MinIO).
- `pipelines/pyproject.toml` — add `paddleocr`, `pdf2image` (or `pymupdf`),
  `Pillow`, `google-generativeai` (for E2 only; remove if Sonnet wins).

## Risk register

| Risk | Mitigation |
|---|---|
| PDF URL rot before backfill completes (RE/MAX session-gated 8% coverage) | `floor_plan_ingest_dag` runs as soon as new listings land; fetch errors logged but don't block; manual re-fetch script for stale URLs. |
| Vision-LLM cost overrun if dedup rate is worse than estimated | sha256 dedup at blob layer; OCR-first hybrid (E1 gates); per-run cost budget alert in DAG. |
| Zome `areas_extras` taxonomy doesn't generalize across portals (e.g. JLL plans show "marquise", "alpendre", etc.) | `space_type_observed_raw` preserves any label; quarterly review of unmapped raw labels; closed-9 is a deliberate choice and lossy labels are surfaced not silenced. |
| Multi-floor confusion → phantom duplicate rooms | `floors_depicted` array in output schema forces per-floor structuring; silver dedup logic uses `(floor_ordinal, space_type, area±10%)` as the dedup key. |
| Legacy 1,473 rows have lower quality than v1 (different prompt, no plan_classification gate) | `source='cv_floor_plan_v0_legacy'` distinguishes; downstream analytics can filter or downweight; consider re-running v1 over the same Idealista plans once v1 stabilizes. |
| `hall/escritorio/arrumos` data appears worth keeping after all | Re-open closed-9 to closed-12; one-line enum doc change + post-process taxonomy map update. No table migration (those rows already have raw label preserved). |

## Glossary (for future Claude reading cold)

- **`areas_extras`**: Zome bronze JSONB column; per-space area breakdown.
  See [`wiki/sources/zome.md`](../../../sources/zome.md).
- **`aplantsgallery`**: Zome bronze JSONB column; floor plan image URLs.
  Same source page.
- **Suite (PT real estate)**: a bedroom with a private bathroom inside.
  Distinct enum value from `bedroom`.
- **T1/T2/.../T5+**: Portuguese typology = bedroom count.
  T2 = 2-bedroom apartment.
- **Quarto vs suite**: `quarto` = regular bedroom; `suite` = en-suite bedroom.
  Distinguished in `areas_extras` and the v1 enum.
- **`image_full` vs `image_preview`**: the same logical plan stored at two
  resolutions — full for CV input, preview for human verification UI.

## Provenance of this plan

Interview-driven design, 13 question rounds with the user 2026-06-07.
Every architectural fork documented in the Q-numbered sections above.
No decision in this plan was made unilaterally by the agent — all yes/no
gates and either/or choices have a user-confirmed answer in the
interview log.
