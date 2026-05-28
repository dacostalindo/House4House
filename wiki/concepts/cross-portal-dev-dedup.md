---
title: Cross-portal development de-duplication
type: concept
last_verified: 2026-05-22
tags: [silver, cross_portal, dedup, name_matching, slice_b_prime]
---

## For future Claude

This note is a concept about how `silver_unified_developments` collapses the four listing portals' development records (idealista, RE/MAX, Zome, JLL) into one row per real-world marketed development. The matching is **name-driven, not proximity-driven** — portal coordinates routinely disagree by 200-300m+ for the same project, so spatial clustering can't be the grouping key. SCE buildings are deliberately *not* merged here.

## What it is

`silver_unified_developments` is the dbt table that holds one row per marketed real-estate development across the [[idealista]], [[remax]], [[zome]], and [[jll]] portals. Each row carries `portal_refs` (every contributing portal record), `portal_unit_counts` (per-portal counts — no laundered "authoritative" number), a unified geometry, and a `geo_key` resolved against [[dim_geography]] via point-in-polygon.

It is the v1-wedge silver foundation that lets `gold.fn_assess_polygon` (the Atlas Inspector's "Nearby developments" surface) display *"this neighborhood has 3 marketed developments"* instead of *"this neighborhood has 12 portal listings, some of which are the same"*.

Shipped in sprint-09 Slice B-prime.

## Why

The portals re-list the same physical development under different names, coordinates, and unit counts. Without de-duplication, `fn_assess_polygon` returns N portal pages per dev, and the Inspector either double-counts or has to dedup at query time.

Three structural facts made the design non-obvious:

1. **Portal coordinates disagree by 200-300m+ for the same development.** Empirical evidence (2026-05-22 audit, Aveiro):
   - "The Unique" — idealista vs RE/MAX, 233m apart.
   - "JC Barrocas Apartments" — idealista vs Zome, 293-317m apart.
   - "Domus Ria" — idealista vs RE/MAX, *18m* apart (lucky alignment).
   This kills proximity-first clustering: a 50m DBSCAN eps would split same-dev listings; a generous eps would over-merge unrelated devs in dense urban blocks.

2. **Project names are not byte-identical across portals.** Idealista's "The Unique" vs RE/MAX's "Unique" (different "the" prefix); Zome's "Empreendimento JC Barrocas Apartments" vs idealista's "JC Barrocas Apartments" (Zome's `empreendimento` prefix); typology codes like `T1+1` and trailing concelho names ("…, Matosinhos") drag fuzzy ratios below threshold. Raw Levenshtein ratio scores these at 0.59-0.60 — borderline — when they should be exact matches.

3. **SCE buildings and portal developments are different concepts.** [[silver_sce_buildings]] is a physical building with energy certificates; a portal development is a marketed project. They have no shared identifier (no project name on SCE, no cadastral ID on portals, no shared address grain) and incompatible geocoding precision (Nominatim street centroid vs portal pins). The Slice B-prime exploration tried filtering SCE buildings (≥5 frações; ≤2.5y certs; with/without idealista) and the best result was 4 of 11 Aveiro portal-anchored devs matched, with low confidence. The structure resists clean merging.

## How

`silver_unified_developments` is name-driven Phase 1 only — no Phase 2, no SCE.

**Name normalization** — applied to each portal's `canonical_name`:

1. Lowercase + deaccent (Portuguese vowels and `ç` → ASCII).
2. Strip typology codes: `\m t[0-9]+([-+/][0-9]+)* \M` — kills `T1`, `T2`, `T1+1`, `T2-3`, etc.
3. Strip boilerplate words: `\m(empreendimento|edificio|the)\M` — anywhere in the string.
4. Punctuation → space → collapse → trim.
5. Strip a *trailing* concelho name (handles "UNIQUE - Padrão da Légua, Matosinhos" → "unique padrao da legua").

**Word-set Jaccard** — names are compared as token bags:

- `jaccard(A, B) = |A ∩ B| / |A ∪ B|`
- Two listings are linked when Jaccard ≥ 0.6 AND they share a concelho AND (either coord is missing OR they are within 1km).
- Token-based, not character-based — chosen specifically because the distortions are *whole boilerplate words*, not character typos. Levenshtein fails on prefix insertions; Jaccard handles them naturally ("jc barrocas apartments" ⊆ "jc barrocas apartments" → 1.0 after stripping `empreendimento`).

**Connected components** over the link graph give the final development grouping. A recursive CTE walks the undirected edges (plus self-loops so singletons get a component); each member's `dev_key` is the smallest `member_id` it can reach.

**Geometry hierarchy** — when a development has members on multiple portals, the unified geom + concelho + parish come from the highest-priority portal that has coordinates: **JLL > Zome > RE/MAX > idealista**. Locked 2026-05-22 by user decision; reflects per-portal geo-quality trust (JLL = curated GPS with reliability flag; idealista = average of unit geocodes, last because the average smears for spread-out developments).

**Unit counts** — `portal_unit_counts` (JSONB) exposes every portal's reported `total_units` without picking an "authoritative" number. The portals report counts with heterogeneous semantics:

- idealista — *listed-units subset*, not the development total (2026-05-22 facade audit: "The Unique" listed as 3 units, facade shows ~50+).
- Zome — inventory (available + reserved + sold).
- JLL — `total_fractions`.
- RE/MAX — listings at RE/MAX (subset).

Consumers read the breakdown and choose. The earlier Decision 9 (`total_units_authoritative = GREATEST(SCE count, MAX(portal))`) was retired when SCE matching was removed — there's no longer a reliable anchor to compute "authoritative" against.

**Why SCE is not merged here** — every attempt to match SCE buildings to portal developments produced low-confidence matches:

- Spatial proximity is noisy (Nominatim street-centroid SCE vs portal pins).
- No shared identifier — SCE has no project name; portals don't expose cadastral `matrix_article`.
- Street-address match works for idealista/JLL but not RE/MAX/Zome (which expose only parish + concelho).
- After stacking constraints (≥5 frações, ≤2.5y certs, no-idealista) the best Aveiro result was 4 of 11 portal-anchored devs matched, with the rest of the table dominated by promoted SCE-only rows that aren't "developments" in the marketed sense.

The reframe: SCE buildings and portal developments are different concepts. `silver_unified_developments` = marketed developments; [[silver_sce_buildings]] = certified buildings. `fn_assess_polygon` queries **both side-by-side** ("3 marketed developments + 26 certified buildings near here") rather than forcing them into one row.

**`geo_key` resolution** — point-in-polygon of the unified geom against `dim_geography.freguesia_geom_pt` via a `LATERAL ... LIMIT 1` (won't double-match). Authoritative INE/CAOP geography, no fuzzy text matching of portal concelho strings.

## See also

- [[silver_sce_buildings]] — the sister table holding physical buildings with energy certificates; queried alongside, not merged.
- [[sce-buildings-clustering]] — the SCE-side equivalent concept (DBSCAN + fração-grain dedup).
- [[portal-field-map]] — the per-portal field-mapping reference that made Phase 1 normalization possible.
- [[idealista]], [[remax]], [[zome]], [[jll]] — the four contributing portals.
- [[sprint-09]] — the sprint this shipped in (Slice B-prime).
