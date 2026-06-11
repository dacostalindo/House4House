---
title: S+1 — Surface Zome's per-room areas into silver
type: plan
last_verified: 2026-06-07
tags: [sprint, floor-plan-cv, silver, zome]
status: planned
sprint: s1
estimated_effort: 1 week
---

# S+1 — Surface Zome's per-room areas into silver

## For future Claude

This is a plan page for **Sprint 1** of the floor-plan CV project — pure
SQL work that unpivots [[zome]]'s `areas_extras` JSONB into a long-format
silver model. Architectural background lives in
[[planning/PoCs/floor-plan-cv/design]]; this file holds the task breakdown.
Status: planned. Read when picking up S+1 or planning a PR that touches
`unified_listing_spaces`.

**Goal:** Make `bronze_listings.zome_listings.areas_extras` queryable in
silver as a long-format `unified_listing_spaces` model with `source='zome_native'`.
No ML, no CV — pure SQL unpivot. Delivers value immediately for the 1,447
labelled Zome listings.

**Depends on:** nothing.
**Blocks:** S+5 (needs silver model to exist before legacy migration lands).

---

## ✓ T1.0 — Source YAML description (already shipped)

**What:** `areas_extras` description in `_staging_listings__sources.yml`
expanded from one-liner to full spec with shape, coverage, ground-truth role.

**Files:** `dbt/models/staging/listings/_staging_listings__sources.yml:1063`

**Acceptance:** done in PR #57. No further work.

---

## T1.1 — Build `stg_portal_spaces_zome.sql`

**What:** Staging model that unpivots `bronze_listings.zome_listings.areas_extras`
into long format. One row per `(listing_id, space_type, ordinal, area_m2)`.

**Files:**
- `dbt/models/staging/portals/stg_portal_spaces_zome.sql` (new)
- `dbt/models/staging/portals/_staging_portals__models.yml` (add model entry; check exact filename)

**Implementation sketch (SQL):**
```sql
WITH src AS (
    SELECT
        listing_id,
        areas_extras
    FROM {{ source('zome', 'zome_listings') }}
    WHERE areas_extras IS NOT NULL
      AND areas_extras::text <> '{"wcs": [], "rooms": [], "suite": [], "garage": [], "garden": [], "balcony": [], "kitchen": [], "terrace": [], "livingRoom": []}'
),
unpacked AS (
    SELECT
        listing_id,
        key   AS zome_key,
        value AS area_array
    FROM src, jsonb_each(areas_extras)
    WHERE jsonb_array_length(value) > 0
),
exploded AS (
    SELECT
        listing_id,
        zome_key,
        ordinality::SMALLINT             AS ordinal,
        area_text::NUMERIC               AS area_m2
    FROM unpacked,
         jsonb_array_elements_text(area_array) WITH ORDINALITY AS t(area_text, ordinality)
)
SELECT
    'zome|' || listing_id::TEXT                          AS listing_uid,
    CASE zome_key
        WHEN 'rooms'      THEN 'bedroom'
        WHEN 'suite'      THEN 'bedroom_suite'
        WHEN 'wcs'        THEN 'bathroom'
        WHEN 'kitchen'    THEN 'kitchen'
        WHEN 'livingRoom' THEN 'living_room'
        WHEN 'balcony'    THEN 'balcony'
        WHEN 'terrace'    THEN 'terrace'
        WHEN 'garden'     THEN 'garden'
        WHEN 'garage'     THEN 'garage'
    END                                                  AS space_type,
    ordinal,
    area_m2,
    'zome_native'                                        AS source,
    NULL::NUMERIC                                        AS confidence,
    zome_key                                             AS space_type_observed_raw,
    NULL::JSONB                                          AS bbox_pct,
    NULL::TEXT                                           AS model_version,
    NULL::TEXT                                           AS plan_image_hash,
    CURRENT_TIMESTAMP                                    AS extracted_at  -- replace with bronze valid_from
FROM exploded
```

**Acceptance:**
- `dbt run --select stg_portal_spaces_zome` succeeds.
- Row count = sum of array lengths across populated `areas_extras` (sanity-check against ~4,000–6,000 rows from the 1,447 listings).
- Zero NULL `space_type` (closed 9-enum maps every Zome key).
- No duplicate `(listing_uid, space_type, ordinal, source)` tuples.

**Depends on:** T1.0.

---

## T1.2 — Build `unified_listing_spaces.sql` skeleton (zome_native only)

**What:** Silver model that's the canonical per-room area table.
S+1 ships it sourced **only** from `stg_portal_spaces_zome`; S+5 widens
it to UNION the CV intermediate.

**Files:**
- `dbt/models/silver/properties/unified_listing_spaces.sql` (new)

**Implementation sketch:**
```sql
{{ config(materialized='table', schema='silver_properties') }}

SELECT * FROM {{ ref('stg_portal_spaces_zome') }}
```

Yes, this S+1 version is a single-source pass-through. S+5 adds the
UNION ALL of `int_floor_plan_cv_predictions`.

**Acceptance:**
- `dbt run --select unified_listing_spaces` succeeds.
- Row count matches T1.1 row count.

**Depends on:** T1.1.

---

## T1.3 — Schema YAML + dbt tests for `unified_listing_spaces`

**What:** Add the model's column docs + tests. Mirrors the convention
in existing silver `_properties__models.yml` files.

**Files:**
- `dbt/models/silver/properties/_unified_listing_spaces.yml` (new)

**Tests to include:**
- `not_null`: `listing_uid`, `ordinal`, `area_m2`, `source`, `extracted_at`
- `accepted_values` on `space_type`: the 9-enum (allowing NULL for unmapped legacy labels post-S+5; for S+1 the test can disallow NULL since only zome_native rows land)
- `accepted_values` on `source`: `['zome_native', 'cv_floor_plan_v1', 'cv_floor_plan_v0_legacy', 'description_nlp_v1', 'manual']`
- `unique` on the 4-column tuple `(listing_uid, space_type, ordinal, source)` via `dbt_utils.unique_combination_of_columns`
- Range test: `area_m2` between 0.5 and 1000 (sanity bounds)

**Acceptance:**
- `dbt test --select unified_listing_spaces` passes.

**Depends on:** T1.2.

---

## T1.4 — Wiki updates

**What:** Per project CLAUDE.md rules, surface the new silver model in
the right wiki cross-refs.

**Files:**
- `wiki/log.md` — one-line entry on commit
- `wiki/sources/zome.md` — add cross-link section: "`areas_extras` is now surfaced in silver via `unified_listing_spaces`. See [planning/PoCs/floor-plan-cv/design.md]."
- `wiki/index.md` §"By area of code" — add `dbt/models/silver/properties/unified_listing_spaces.sql` row
- `wiki/concepts/per-room-areas.md` (new, optional) — concept page explaining the 9-enum, suite vs bedroom distinction, and the long-format silver shape

**Acceptance:**
- Wiki linter passes (`/wiki-lint` skill).
- `wiki/index.md` routes `dbt/models/silver/properties/` to the new concept page.

**Depends on:** T1.3.

---

## Out of scope for S+1

- Any CV, OCR, vision-LLM, MinIO, or floor-plan-image work (S+2, S+3, S+4).
- Idealista/JLL/RE/MAX per-space data (those portals have none natively).
- Plot listings (`bronze_listings.zome_plots`) — plots have no rooms.
- Migrating the 1,473 legacy `floor_plan_extractions` rows (S+5).

## Open questions for S+1

- `extracted_at` value for zome_native rows: `CURRENT_TIMESTAMP` is a
  placeholder. Better source: bronze `_dlt_valid_from`. Pick during
  implementation; the placeholder works for S+1 ship.
- Whether to also expose Zome's `gallery` floor-plan URLs in
  `unified_listing_spaces`-adjacent staging (probably no — that's S+2's job).
