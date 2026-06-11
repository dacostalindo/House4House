---
title: S+2 — Archive floor plans to MinIO with sha256 dedup
type: plan
last_verified: 2026-06-07
tags: [sprint, floor-plan-cv, minio, blob-store, archive]
status: planned
sprint: s2
estimated_effort: 1.5 weeks
---

# S+2 — Archive floor plans to MinIO with sha256 dedup

## For future Claude

This is a plan page for **Sprint 2** of the floor-plan CV project — adds
the MinIO blob layer + ingest DAG that downloads, dedups by SHA256, and
rasterizes PDFs across [[zome]] + [[idealista]] + [[jll]] + [[remax]].
Enables Sprints 3 and 4. Architectural background:
[[planning/PoCs/floor-plan-cv/design]]. Status: planned. Parallel-safe with S+1.

**Goal:** Download every floor plan from the 4 portals into
`s3://raw/floor-plans/by-hash/`, content-addressed by SHA256. PDFs get
rasterized to high-res WebP-lossless; all `image_full` blobs get a
WebP-lossy preview. Postgres metadata in two tables: `floor_plan_blob`
(content) + `floor_plan_blob_ref` (listing → blob mapping).

**Depends on:** nothing (parallel-safe with S+1).
**Blocks:** S+3 (needs blobs to experiment on).

---

## T2.1 — Verify MinIO `raw` bucket + `floor-plans/by-hash/` prefix

**What:** Confirm existing MinIO container has the `raw` bucket and that
the prefix `raw/floor-plans/by-hash/` is writable. No new infra; reuse
the existing `pipelines/scraping/template/scraping_bronze_template.py`
Minio client pattern.

**Files:** none (verification only)

**Acceptance:**
- `mc ls s3://raw/` (or equivalent) lists the existing scrape data.
- A test put/get round-trip via the existing `minio==7.2.7` client
  succeeds at `s3://raw/floor-plans/by-hash/test.txt`.

**Depends on:** nothing.

---

## T2.2 — `pipelines/media/blob_store.py` — content-hash addressing helpers

**What:** Small module providing:
- `compute_sha256(bytes) -> str`
- `storage_uri(sha256: str, ext: str) -> str` → `s3://raw/floor-plans/by-hash/{sha[:2]}/{sha[2:4]}/{sha}.{ext}`
- `put_blob(client, bytes, sha256, ext, mime_type)` — idempotent upload (skip if key exists)
- `get_blob(client, sha256, ext) -> bytes`
- `MinIO client factory` reading Airflow Variables (`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`) — copy from `scraping_bronze_template.py`

**Files:**
- `pipelines/media/__init__.py` (new)
- `pipelines/media/blob_store.py` (new)

**Acceptance:**
- Unit test: same bytes hash to same key (idempotent).
- Round-trip: `put_blob` then `get_blob` returns identical bytes.

**Depends on:** T2.1.

---

## T2.3 — Bronze DDL: `floor_plan_blob` + `floor_plan_blob_ref`

**What:** Create the two bronze tables per the schema in the plan doc.
Mirror DDL style of `bronze_listings.floor_plan_extractions` (raw SQL
in a Python task or a dbt seed-style file).

**Files:**
- `pipelines/media/sql/create_floor_plan_blob_tables.sql` (new, raw DDL)
- `dbt/models/staging/listings/_staging_listings__sources.yml` — add source entries for both new tables

**DDL (copy from plan doc § Bronze schemas):**
```sql
CREATE TABLE IF NOT EXISTS bronze_listings.floor_plan_blob (
  sha256              TEXT PRIMARY KEY,
  role                TEXT NOT NULL,
  mime_type           TEXT NOT NULL,
  storage_uri         TEXT NOT NULL,
  bytes_size          INTEGER NOT NULL,
  width_px            INTEGER NULL,
  height_px           INTEGER NULL,
  page_index          SMALLINT NULL,
  derived_from_sha256 TEXT NULL REFERENCES bronze_listings.floor_plan_blob(sha256),
  first_seen_at       TIMESTAMP NOT NULL,
  CHECK (role IN ('pdf_source','image_full','image_preview')),
  CHECK (role <> 'pdf_source' OR (page_index IS NULL AND derived_from_sha256 IS NULL)),
  CHECK (role <> 'image_preview' OR derived_from_sha256 IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_fpb_role ON bronze_listings.floor_plan_blob(role);
CREATE INDEX IF NOT EXISTS idx_fpb_derived ON bronze_listings.floor_plan_blob(derived_from_sha256);

CREATE TABLE IF NOT EXISTS bronze_listings.floor_plan_blob_ref (
  portal             TEXT NOT NULL,
  source_listing_id  TEXT NOT NULL,
  ordinal            SMALLINT NOT NULL,
  sha256             TEXT NOT NULL REFERENCES bronze_listings.floor_plan_blob(sha256),
  source_url         TEXT NOT NULL,
  fetched_at         TIMESTAMP NOT NULL,
  PRIMARY KEY (portal, source_listing_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_fpbr_sha ON bronze_listings.floor_plan_blob_ref(sha256);
```

**Acceptance:**
- Both tables created in `bronze_listings`.
- Source YAMLs lint cleanly (`dbt parse`).
- CHECKs reject illegal states (manual INSERT test).

**Depends on:** nothing.

---

## T2.4 — PDF rasterization module

**What:** Rasterize PDF pages to WebP-lossless at 3000 px on the long side.
Uses `pymupdf` (faster + less native deps than `pdf2image`).

**Files:**
- `pipelines/media/rasterize.py` (new)
- `pipelines/pyproject.toml` — add `pymupdf`, `Pillow`

**API:**
```python
def rasterize_pdf(pdf_bytes: bytes, target_long_side_px: int = 3000)
    -> list[tuple[int, bytes, int, int]]:
    """Return [(page_index_1based, webp_lossless_bytes, width_px, height_px), ...]"""
```

**Acceptance:**
- Test PDF (sample JLL plan) rasterizes to N images with correct page count.
- Long side ≤ 3000 px; aspect ratio preserved.
- Output is valid WebP-lossless (decodes back to the same dimensions).

**Depends on:** nothing.

---

## T2.5 — WebP preview generator

**What:** Generate 1024 px long-side WebP-lossy q80 preview from any image.

**Files:**
- `pipelines/media/preview.py` (new) — single function

**API:**
```python
def generate_preview(image_bytes: bytes, target_long_side_px: int = 1024, quality: int = 80) -> tuple[bytes, int, int]:
    """Returns (webp_lossy_bytes, width_px, height_px)."""
```

**Acceptance:**
- Output ≤ ~100 KB on typical floor-plan input.
- Long side ≤ 1024 px; aspect preserved.

**Depends on:** T2.4 (shared Pillow setup).

---

## T2.6 — `floor_plan_ingest_dag.py`

**What:** The main DAG. Iterates `floor_plan_urls` across all 4 portal-listings
bronze tables, downloads new URLs, dedups by SHA256, rasterizes PDFs,
generates previews, uploads everything to MinIO, writes
`floor_plan_blob` + `floor_plan_blob_ref` rows in one transaction.

**Files:**
- `pipelines/media/floor_plan_ingest_dag.py` (new)

**Logic outline:**
1. **Source URL discovery** — UNION of `floor_plan_urls` arrays across:
   - `bronze_listings.zome_listings.aplantsgallery->'hres'` (JSONB array)
   - `bronze_listings.idealista_*` floor-plan-tagged URLs (check existing `stg_portal_listings_idealista` for the extract logic)
   - `bronze_listings.jll_*` `blue_prints` JSONB
   - `bronze_listings.remax_*` `floor_plan_path` (URL = `https://i.maxwork.pt/bb` + path)
2. **Skip already-fetched** — LEFT JOIN `floor_plan_blob_ref` on `(portal, source_listing_id, ordinal)`.
3. **Download** — `requests` with 30s timeout, tenacity retry on 5xx (not on 4xx). Log fetch errors to task logs; skip the row.
4. **Classify** — sniff content-type. If PDF: store as `pdf_source` + rasterize → N `image_full` rows. If JPG/WebP/PNG: store as `image_full` (no `pdf_source` row).
5. **Generate preview** — for each `image_full`, run preview generator → `image_preview` row.
6. **Upload + write** — `put_blob` for each, then INSERT into both tables in one TX. Use `ON CONFLICT (sha256) DO NOTHING` on `floor_plan_blob` (dedup).
7. **Trigger:** runs after each portal's bronze refresh (Airflow `ExternalTaskSensor` or trigger rule).

**Acceptance:**
- DAG passes `airflow dags test floor_plan_ingest_dag <date>` on a dry-run with a small fixture (5 plans across 4 portals).
- On a 100-plan sample, expected ≥30% dedup hit rate (developer-shared plans).
- `floor_plan_blob_ref.fetched_at` populated; CHECK constraints satisfied.
- Failed fetches don't break the DAG — logged + skipped.

**Depends on:** T2.2, T2.3, T2.4, T2.5.

---

## T2.7 — Full backfill across 4 portals

**What:** Run `floor_plan_ingest_dag` over the full existing bronze data
(no `since` filter). Monitor dedup hit rate; expect ~30–50% storage
savings from shared developer plans.

**Files:** none (operational)

**Acceptance:**
- All 4 portals' floor plan URLs processed (with documented failure rate per portal — RE/MAX's 8% coverage may have high 404 rate).
- Total `floor_plan_blob` row count + total bytes documented in wiki sprint log.
- `bronze_listings.zome_listings`: ≥6,000 of the 6,834 plan-bearing listings have at least one `image_full` blob.
- Operational report appended to `wiki/log.md`.

**Depends on:** T2.6.

---

## Out of scope for S+2

- Any CV inference (S+3, S+4).
- The Idealista `image_classification_dag` task group A refactor — that
  stays as-is during S+2.
- Public-facing image serving (e.g. signed URLs for Streamlit). MinIO has
  it but no consumer needs it yet.

## Open questions for S+2

- Whether to also store an `archive` flag on `floor_plan_blob_ref` for
  URLs that 404'd post-fetch (currently the row exists, the source URL
  may have rotted). Probably out of scope; revisit in S+4 when CV needs
  re-fetch behavior.
- PDF page limit. If a single PDF has >50 pages (unlikely but possible),
  do we rasterize all or cap? Cap at 20 pages with a warning, revisit if
  any real plan needs more.
- MinIO retention policy. Plans are valuable; no expiration. Add a
  lifecycle rule? Probably no — storage is local-disk, not S3.
