---
title: S+3 — Experiments E1 (OCR yield) + E2 (Sonnet vs Gemini bake-off)
type: plan
last_verified: 2026-06-07
tags: [sprint, floor-plan-cv, experiments, ocr, vision-llm, bake-off]
status: planned
sprint: s3
estimated_effort: 3 days
---

# S+3 — Experiments E1 + E2

## For future Claude

This is a plan page for **Sprint 3** of the floor-plan CV project — two
empirical experiments (OCR yield + Sonnet vs Gemini bake-off) that gate
Sprint 4's architecture and model choice. Architectural background:
[[planning/PoCs/floor-plan-cv/design]]. Status: planned. Depends on S+2 blobs.

**Goal:** Two empirical decisions that gate S+4's architecture:
- **E1 — OCR yield.** Decides whether to ship OCR-first hybrid or vision-LLM-only.
- **E2 — Model bake-off.** Decides Claude Sonnet 4.5 vs Gemini 2.5 Pro for the vision-LLM half.

**Depends on:** S+2 (needs `image_full` blobs to experiment on).
**Blocks:** S+4 (architecture + model choice fall out of these results).

---

## T3.1 — Create `metadata.cv_floor_plan_experiment` table

**What:** Disposable table for experiment runs. Not silver, not gold,
not consumed by analytics.

**Files:**
- `pipelines/enrichment/floor_plan_cv/sql/create_experiment_table.sql` (new)

**DDL:**
```sql
CREATE SCHEMA IF NOT EXISTS metadata;

CREATE TABLE IF NOT EXISTS metadata.cv_floor_plan_experiment (
  experiment_id    TEXT NOT NULL,           -- 'e1_ocr_yield' | 'e2_model_bakeoff_sonnet' | 'e2_model_bakeoff_gemini'
  blob_sha256      TEXT NOT NULL REFERENCES bronze_listings.floor_plan_blob(sha256),
  listing_uid      TEXT NULL,                -- populated if blob belongs to a labelled-set listing
  model            TEXT NOT NULL,            -- 'paddleocr-pt-v1' | 'claude-sonnet-4-5' | 'gemini-2.5-pro'
  prompt_version   SMALLINT NULL,            -- NULL for OCR
  payload          JSONB NOT NULL,           -- raw model output
  cost_usd         NUMERIC(10,6) NULL,       -- NULL for OCR
  latency_ms       INTEGER NOT NULL,
  run_at           TIMESTAMP NOT NULL,
  PRIMARY KEY (experiment_id, blob_sha256, model)
);
```

**Acceptance:**
- Table exists in `metadata` schema.
- FK to `floor_plan_blob` enforced.

**Depends on:** S+2 (table referenced).

---

## T3.2 — E1: OCR yield sampling

**What:** Run PaddleOCR with the Portuguese language pack on 100
stratified `image_full` blobs. Stratify by portal (zome, idealista, jll,
remax) and by plan type (single-floor vs multi-floor). Measure how
often we extract clean `(room_label, area_m2)` pairs.

**Files:**
- `pipelines/enrichment/floor_plan_cv/ocr.py` (new) — PaddleOCR wrapper, label/area regex extractor
- `pipelines/enrichment/floor_plan_cv/e1_run.py` (new) — one-shot script
- `pipelines/pyproject.toml` — add `paddleocr`, `paddlepaddle` (CPU)

**Sampling SQL:**
```sql
-- 25 per portal, mixed plan types
WITH stratified AS (
  SELECT b.sha256, r.portal, r.source_listing_id,
         ROW_NUMBER() OVER (PARTITION BY r.portal ORDER BY md5(b.sha256)) AS rn
  FROM bronze_listings.floor_plan_blob b
  JOIN bronze_listings.floor_plan_blob_ref r ON r.sha256 = b.sha256
  WHERE b.role = 'image_full'
)
SELECT sha256, portal, source_listing_id
FROM stratified
WHERE rn <= 25;
```

**Output payload shape** (per blob row in `metadata.cv_floor_plan_experiment`):
```json
{
  "raw_text_lines": ["Sala 22 m²", "Quarto 1", "14.3 m²", ...],
  "extracted_pairs": [{"label":"Sala","area_m2":22.0,"line_idx":3}],
  "n_lines_total": 47,
  "n_pairs_extracted": 8
}
```

**Decision metrics** (compute in a notebook or SQL on the experiment table):
- % of plans with ≥1 clean `(label, area)` pair
- % of plans where ≥50% of expected spaces (proxied by Zome `areas_extras` count where available) extract
- Per-portal yield breakdown

**Acceptance:**
- 100 rows in `metadata.cv_floor_plan_experiment` with `experiment_id='e1_ocr_yield'`.
- A 1-page summary written to `wiki/decisions/2026-06-XX-floor-plan-cv-ocr-vs-llm.md` recording the yield numbers and the architecture decision (hybrid vs LLM-only).

**Decision criterion (from plan doc):**
- ≥60% yield → ship OCR-first hybrid
- 30–60% → hybrid with high LLM fallback rate; ship anyway
- <30% → drop OCR, vision-LLM-only

**Depends on:** T3.1, S+2.

---

## T3.3 — E2: Vision-LLM bake-off (Sonnet 4.5 vs Gemini 2.5 Pro)

**What:** Run both models against the same 100-blob stratified sample,
intersected with the 1,230-listing Zome labelled set so we have ground truth.
Identical prompts (from the plan doc's 6-section structure), identical
structured-output schema.

**Files:**
- `pipelines/enrichment/floor_plan_cv/prompts.py` (new) — 6-section template, `prompt_version=1`
- `pipelines/enrichment/floor_plan_cv/schema.py` (new) — Pydantic models for the payload (mirror `plot_listing_extraction/schema.py`)
- `pipelines/enrichment/floor_plan_cv/vision_llm.py` (new) — two clients: `AnthropicVision`, `GeminiVision`, both returning the same Pydantic shape
- `pipelines/enrichment/floor_plan_cv/e2_run.py` (new) — one-shot script
- `pipelines/pyproject.toml` — add `google-genai` (experimental; remove if Sonnet wins)

**Sample selection SQL:**
```sql
-- Blobs from zome listings with populated areas_extras (the 1,230 set)
WITH labelled AS (
  SELECT l.listing_id::TEXT AS source_listing_id, l.areas_extras
  FROM bronze_listings.zome_listings l
  WHERE l.areas_extras IS NOT NULL
    AND l.areas_extras::text <> '{"wcs": [], "rooms": [], "suite": [], ...}'
    AND jsonb_array_length(COALESCE(l.aplantsgallery->'hres','[]'::jsonb)) > 0
),
sampled AS (
  SELECT r.sha256, l.source_listing_id, l.areas_extras,
         ROW_NUMBER() OVER (ORDER BY md5(r.sha256)) AS rn
  FROM bronze_listings.floor_plan_blob_ref r
  JOIN labelled l ON r.portal = 'zome' AND r.source_listing_id = l.source_listing_id
  JOIN bronze_listings.floor_plan_blob b ON b.sha256 = r.sha256
  WHERE b.role = 'image_full'
)
SELECT * FROM sampled WHERE rn <= 100;
```

**Per-blob output** (one row per `(blob, model)` pair):
- Full structured payload per plan doc's schema
- `cost_usd` computed from token usage
- `latency_ms` measured

**Metrics computed in analysis notebook:**
- Per-space-type MAE on `area_m2` (pred vs true)
- Count F1 per space_type
- Suite/bedroom confusion matrix
- Refusal rate (`plan_classification != 'residential_floor_plan'`)
- Avg cost per plan, per model
- p50 / p95 latency per model

**Decision criterion (from plan doc):**
- Cheaper unless quality gap on MAE >15%.

**Acceptance:**
- 200 rows in `metadata.cv_floor_plan_experiment` (100 per model) with `experiment_id IN ('e2_model_bakeoff_sonnet', 'e2_model_bakeoff_gemini')`.
- Per-model summary table in `wiki/decisions/2026-06-XX-floor-plan-cv-model-choice.md` with the comparison metrics + locked decision.
- A v1 `prompts.py` + `schema.py` survives into S+4 (not throwaway).

**Depends on:** T3.1, S+2.

---

## T3.4 — Confidence-threshold calibration (preview)

**What:** Using the same E2 data, compute the confidence-vs-accuracy curve
per model. This is what informs the production `confidence ≥ X` filter
(deferred from Q11 in the plan doc).

**Files:**
- Inline in the E2 analysis notebook; commit the curve as `wiki/decisions/.../confidence-calibration.png` and document the chosen threshold.

**Acceptance:**
- Chart shows accuracy (MAE or absolute error <1 m²) by confidence bucket [0–0.3, 0.3–0.5, 0.5–0.7, 0.7–0.9, 0.9–1.0].
- A threshold is picked + recorded for use in T4.6.

**Depends on:** T3.3.

---

## Out of scope for S+3

- Production CV (S+4).
- Silver wiring (S+5).
- Any code outside `pipelines/enrichment/floor_plan_cv/`.
- Eval on non-Zome portals (no ground truth there).

## Open questions for S+3

- Does PaddleOCR-PT handle handwriting-style architect-drawn plans? If
  yields are low for that subset, document separately — those plans may
  always need vision-LLM.
- Gemini 2.5 Pro structured-output API surface vs Claude's tool-use:
  pick the abstraction in `vision_llm.py` that exposes both cleanly.
  Pydantic models as the contract help here.
- Sample size of 100 — too small for tight CIs on MAE per space_type
  (some types have <5 instances). If E2 is inconclusive, scale to 300.
  Budget: 300 × 2 models × ~$0.02 = $12, trivial.
