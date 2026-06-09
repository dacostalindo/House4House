---
title: S+4 — CV production pipeline
type: plan
last_verified: 2026-06-07
tags: [sprint, floor-plan-cv, vision-llm, ocr, airflow, bronze]
status: planned
sprint: s4
estimated_effort: 1.5 weeks
---

# S+4 — CV production pipeline

**Goal:** Ship `floor_plan_cv_dag` running the architecture + model picked
in S+3. Output lands in `bronze_listings.floor_plan_cv_prediction`.
Production excludes the 1,230 Zome listings that have populated
`areas_extras` (Q6.b decision); a separate benchmark run scores a
stratified 200-blob sample for the calibration table.

**Depends on:** S+3 (architecture + model locked).
**Blocks:** S+5 (needs CV rows in bronze before silver wires them in).

---

## T4.1 — `bronze_listings.floor_plan_cv_prediction` table

**What:** Create the production CV output table per the plan doc schema.

**Files:**
- `pipelines/enrichment/floor_plan_cv/sql/create_prediction_table.sql` (new)
- `dbt/models/staging/listings/_staging_listings__sources.yml` — source entry

**DDL:**
```sql
CREATE TABLE IF NOT EXISTS bronze_listings.floor_plan_cv_prediction (
  blob_sha256       TEXT NOT NULL REFERENCES bronze_listings.floor_plan_blob(sha256),
  model             TEXT NOT NULL,
  prompt_version    SMALLINT NOT NULL,
  payload           JSONB NOT NULL,
  extraction_status TEXT NOT NULL,
  error_message     TEXT NULL,
  extracted_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (blob_sha256, model, prompt_version),
  CHECK (extraction_status IN ('success','refused','schema_error','http_error'))
);

CREATE INDEX IF NOT EXISTS idx_fpcp_status ON bronze_listings.floor_plan_cv_prediction(extraction_status);
CREATE INDEX IF NOT EXISTS idx_fpcp_extracted_at ON bronze_listings.floor_plan_cv_prediction(extracted_at);
```

**Acceptance:**
- Table created.
- Source YAML lints.
- Manual INSERT round-trip works.

**Depends on:** S+2.

---

## T4.2 — Pydantic schema module (production version)

**What:** Promote the experimental `schema.py` from S+3 into a production
module with strict validation, versioned types, and the `report_floor_plan`
tool definition for Anthropic SDK.

**Files:**
- `pipelines/enrichment/floor_plan_cv/schema.py` (promoted from S+3, hardened)

**Key Pydantic models:**
```python
class Space(BaseModel):
    observed_raw_label: str
    space_type: Optional[Literal[
        'bedroom','bedroom_suite','bathroom','kitchen','living_room',
        'balcony','terrace','garden','garage'
    ]] = None  # post-process can set to None if observed_raw doesn't map
    area_m2: float = Field(gt=0, lt=1000)
    area_source: Literal['annotated_on_plan','inferred_from_scale','refused']
    is_suite: bool = False
    bbox_pct: Optional[BboxPct] = None
    confidence: float = Field(ge=0, le=1)

class Floor(BaseModel):
    floor_label: str = ""
    floor_ordinal: int = Field(ge=1)
    spaces: list[Space]

class FloorPlanReport(BaseModel):
    plan_classification: Literal[
        'residential_floor_plan','site_plan','section_diagram',
        'elevation','exterior_photo','not_a_plan','ambiguous'
    ]
    page_classification_confidence: float = Field(ge=0, le=1)
    floors_depicted: list[Floor]
    refusal_reason: Optional[str] = None
```

Mirror `plot_listing_extraction/schema.py` for headers, docstrings, version
comment style.

**Acceptance:**
- `import` succeeds.
- Pydantic round-trip of the plan doc's example payload validates clean.
- Tool-use schema export (`FloorPlanReport.model_json_schema()`) is accepted
  by Anthropic SDK as a tool definition.

**Depends on:** S+3 (T3.3).

---

## T4.3 — Taxonomy module (PT label → 9-enum)

**What:** Python lookup table mapping observed Portuguese labels to the
9-enum. Includes the legacy `hall/escritorio/arrumos` → NULL mapping for
later use in S+5 migration.

**Files:**
- `pipelines/enrichment/floor_plan_cv/taxonomy.py` (new)

**Shape:**
```python
PT_LABEL_TO_SPACE_TYPE: dict[str, Optional[str]] = {
    # Direct hits
    "sala": "living_room",
    "sala comum": "living_room",
    "sala estar": "living_room",
    "cozinha": "kitchen",
    "kitchenette": "kitchen",
    "quarto": "bedroom",
    "suite": "bedroom_suite",
    "wc": "bathroom",
    "casa de banho": "bathroom",
    "varanda": "balcony",
    "terraço": "terrace",
    "terraco": "terrace",
    "jardim": "garden",
    "garagem": "garage",
    # Legacy unmapped (preserved as raw, NULL space_type)
    "hall": None,
    "escritório": None,
    "escritorio": None,
    "arrumos": None,
    # Add more as the unmapped-label metadata report surfaces them
}

def bucket(observed_raw_label: str) -> Optional[str]:
    """Normalize then look up. Returns None for unmapped labels."""
    key = observed_raw_label.strip().lower()
    return PT_LABEL_TO_SPACE_TYPE.get(key)
```

**Acceptance:**
- Unit tests covering each direct hit + 3 NULL hits + 3 misses.
- Case-insensitive, accent-tolerant (or document the normalization rule).

**Depends on:** nothing.

---

## T4.4 — Prompt module (production version)

**What:** Production-grade prompts.py with the 6-section structure.
Versioned. Includes the verbatim suite definition.

**Files:**
- `pipelines/enrichment/floor_plan_cv/prompts.py` (promoted from S+3)

**Constants:**
```python
CURRENT_PROMPT_VERSION = 1

FLOOR_PLAN_SYSTEM_PROMPT = """\
You extract per-room floor areas from Portuguese real-estate floor plans.

[2. Output contract] Call the `report_floor_plan` tool. Do not respond in prose.

[3. Plan classification] If the image is not a residential floor plan ...

[4. Suite definition] `bedroom_suite` = a bedroom with a bathroom located
inside it. If you cannot trace a door from the bedroom into a private WC,
the bedroom is `bedroom`.

[5. Area extraction policy] ...

[6. Multi-floor] ...
"""
```

(Full text per plan doc § Prompt structure.)

**Acceptance:**
- Prompt string parses; no escaped-char surprises.
- E2 bake-off used `prompt_version=1`; this module is the same text.

**Depends on:** S+3 (T3.3) — the prompt text is locked there.

---

## T4.5 — OCR + Vision-LLM client modules (gated on S+3 outcome)

**What:** Hardened versions of the S+3 clients.

**Files (if OCR-hybrid won):**
- `pipelines/enrichment/floor_plan_cv/ocr.py` (promoted, with the
  `(label, area)` extractor → Pydantic `Space` mapping)
- `pipelines/enrichment/floor_plan_cv/vision_llm.py` (promoted; only the
  winning model; the loser's client is deleted)

**Files (if vision-LLM-only won):**
- `pipelines/enrichment/floor_plan_cv/vision_llm.py` only

**Shared interface:**
```python
class Extractor(Protocol):
    def extract(self, image_bytes: bytes, blob_sha256: str) -> FloorPlanReport: ...

class OcrExtractor(Extractor): ...
class VisionLLMExtractor(Extractor): ...

# Hybrid orchestrator
class HybridExtractor:
    def extract(self, image_bytes, blob_sha256):
        ocr_result = self.ocr.extract(image_bytes, blob_sha256)
        if self._ocr_sufficient(ocr_result):
            return ocr_result
        return self.vision_llm.extract(image_bytes, blob_sha256)
```

`_ocr_sufficient` heuristic: e.g. ≥N spaces extracted AND all
`area_source='annotated_on_plan'`. Calibrate against the E2 sample.

**Acceptance:**
- Single-blob extraction round-trip returns a valid `FloorPlanReport`.
- Tenacity retries on API 5xx (not on 4xx) configured.
- Cost + latency logged per call.

**Depends on:** T4.2, T4.3, T4.4, S+3 outcome.

---

## T4.6 — `floor_plan_cv_dag.py`

**What:** Airflow DAG running the extractor over all eligible
`image_full` blobs not yet scored at the current
`(model, prompt_version)`. Writes results to `floor_plan_cv_prediction`.

**Files:**
- `pipelines/enrichment/floor_plan_cv_dag.py` (new)

**Eligibility SQL (selects blobs to score):**
```sql
SELECT b.sha256, b.storage_uri
FROM bronze_listings.floor_plan_blob b
WHERE b.role = 'image_full'
  -- Not yet scored at current model + prompt version
  AND NOT EXISTS (
    SELECT 1 FROM bronze_listings.floor_plan_cv_prediction p
    WHERE p.blob_sha256 = b.sha256
      AND p.model = %(current_model)s
      AND p.prompt_version = %(current_prompt_version)s
  )
  -- Exclude blobs that belong ONLY to listings in the Zome-labelled set
  -- (Q6.b decision: never run production CV on those)
  AND NOT EXISTS (
    SELECT 1
    FROM bronze_listings.floor_plan_blob_ref r
    JOIN bronze_listings.zome_listings l
      ON r.portal = 'zome' AND r.source_listing_id = l.listing_id::TEXT
    WHERE r.sha256 = b.sha256
      AND l.areas_extras::text <> '{"wcs": [], "rooms": [], "suite": [], ...}'
  )
;
```

**Per-blob loop:**
1. Fetch bytes from MinIO via `blob_store.get_blob`.
2. Run extractor (OCR-first or LLM, per S+3 outcome).
3. INSERT into `floor_plan_cv_prediction` with `extraction_status='success'`.
4. On Pydantic validation error → `extraction_status='schema_error'`,
   `payload=raw_text`, `error_message=str(e)`.
5. On API error → `extraction_status='http_error'`.
6. On model refusal (`plan_classification='ambiguous'`) → `extraction_status='refused'`.

**Batching + concurrency:**
- Process in batches of 50; commit per batch.
- Concurrency 4 parallel API calls (configurable).
- Cost budget alert in DAG: if spent > $X per run, fail.

**Acceptance:**
- DAG passes `airflow dags test floor_plan_cv_dag <date>` on a 10-blob fixture.
- Production backfill produces ≥10,000 rows in `floor_plan_cv_prediction`
  (rough estimate: 15k–25k unique blobs after dedup, minus the
  excluded-labelled subset).
- Unmapped-label report appended to wiki (which Portuguese labels appeared
  with no taxonomy mapping → input for T4.3 follow-up).

**Depends on:** T4.1, T4.5.

---

## T4.7 — Benchmark run + `metadata.cv_floor_plan_benchmark`

**What:** Score a stratified 200-blob sample of the **Zome 1,230 labelled
listings** (which production CV explicitly skipped). Compare against
`areas_extras` ground truth. Write to `metadata.cv_floor_plan_benchmark`.

**Files:**
- `pipelines/enrichment/floor_plan_cv/sql/create_benchmark_table.sql` (new)
- `pipelines/enrichment/floor_plan_cv/benchmark_run.py` (new) — one-shot script

**Benchmark table DDL:** per plan doc § Benchmark table.

**Stratified 200-blob selection:**
- 200 listings from the 1,230 set, drawn with strata by:
  - **Typology** (T0..T5+), proportional to set distribution
  - **Plan format** (single-floor image vs multi-floor image)
- Random within strata, seeded for reproducibility

**Metrics to compute (analysis notebook):**
- Per-space-type MAE on area
- Count F1 per space_type
- Suite/bedroom confusion matrix
- Refusal rate
- Plan classification recall
- Confidence calibration curve (final production threshold lands here)

**Acceptance:**
- 200 listings × ~1.85 plans × ~5 spaces ≈ ~1,800–2,500 rows in benchmark table.
- A `wiki/decisions/2026-06-XX-floor-plan-cv-production-threshold.md`
  records the chosen confidence threshold + the per-space MAE numbers.

**Depends on:** T4.6 (uses same extractor code path).

---

## Out of scope for S+4

- Silver wiring (S+5).
- Legacy 1,473-row migration (S+5).
- The Idealista `image_classification_dag` task group A — untouched.

## Open questions for S+4

- Re-run policy when `prompt_version` bumps to 2: do we re-score all old
  predictions, or only newly-failed ones? Default: re-score all, but
  keep old rows (PK includes `prompt_version`). Disk cost is trivial.
- Refusal rate calibration: if >10% of blobs come back `extraction_status='refused'`,
  is that a quality flag (the model is too conservative) or a data signal
  (many `aplantsgallery` images are genuinely not floor plans)? Answer
  empirically with the unmapped-label report + manual review of 20 refusals.
- Self-eval second call (the pattern in `plot_listing_extraction_dag` —
  `extraction_confidence` from a follow-up call): include in v1 or v2?
  Plan doc didn't lock; recommend deferring to v2 to keep v1 single-call.
