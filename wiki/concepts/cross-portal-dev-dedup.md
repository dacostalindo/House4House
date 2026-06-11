---
title: Cross-portal development de-duplication
type: concept
last_verified: 2026-06-09
tags: [silver, cross_portal, dedup, name_matching, slice_b_prime, dev_uid]
---

## Addendum 2026-06-09 — stable `dev_uid` via append-only map + orchestration locked

Two changes from the 2026-06-06 design, landed via the 2026-06-09 orchestration interview:

1. **Identity surface adds `dev_uids[]`.** The volatile `dev_key = MIN(member_id)` stays as a per-run grouping label (renamed `component_id` for clarity), but the row now also carries `dev_uids UUID[]` — the stable identifiers downstream consumers (notably [[UC-4]] LLM dev-actor enrichment) FK against. The `dev_uids` array is sourced from `silver_dev_uid_map`, an append-only `(portal, portal_dev_id) → dev_uid` table. See [[dev-uid-stability]] for the full mechanics, including merge (multiple `dev_uids` in one row) and split (same `dev_uid` in multiple rows) observability.
2. **Orchestration: wall-clock daily silver at `0 11 * * *`, no Airflow Datasets.** Per [[2026-06-09-silver-wall-clock-not-datasets]]: portal scrapers continue on their per-portal crons; silver builds whatever bronze + heartbeat-alive rows it finds at 11:00. Rejected after senior-eng review: Dataset-driven any-of-5 firing was over-engineering for upstreams that are themselves cron, not event-driven.

The Phase 1 normalization pipeline (token + char-trigram dual Jaccard, same-concelho gating, geo-priority hierarchy) is unchanged. The two changes are additive: identity stability and trigger model.

---

## For future Claude

This note is a concept about how `silver_unified_developments` collapses the five listing portals' development records (idealista, RE/MAX, Zome, JLL, imovirtual) into one row per real-world marketed development. The matching is **name-driven, not proximity-driven** — portal coordinates routinely disagree by 200-300m+ for the same project, so spatial clustering can't be the grouping key. SCE buildings are deliberately *not* merged here. Per-row identity carries both a volatile `component_id` (runtime grouping) and a stable `dev_uids UUID[]` array sourced from the append-only [[dev-uid-stability]] map — enrichment pipelines (CV, [[UC-4]] LLM dev-actor) FK on `dev_uid`, never on the volatile column.

## What it is

`silver_unified_developments` is the dbt table that holds one row per marketed real-estate development across the [[idealista]], [[remax]], [[zome]], [[jll]], and [[imovirtual]] portals. Each row carries `portal_refs` (every contributing portal record), `portal_unit_counts` (per-portal counts — no laundered "authoritative" number), a unified geometry, and a `geo_key` resolved against [[dim_geography]] via point-in-polygon.

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

**Name normalization** lives in the `normalize_dev_name()` dbt macro and runs in each staging model. Each portal's `canonical_name` becomes a `match_name` column:

1. Lowercase + deaccent (Portuguese vowels and `ç` → ASCII).
2. Strip typology codes: `\m t[0-9]+([-+/][0-9]+)* \M` — kills `T1`, `T2`, `T1+1`, `T2-3`, etc.
3. Strip boilerplate words: `\m(empreendimento|edificio|the)\M` — anywhere in the string.
4. Punctuation → space → collapse → trim.

The *trailing-concelho strip* (5th step in the v1: "UNIQUE - Padrão da Légua, Matosinhos" → "unique padrao da legua") stays in the silver model because it needs the cross-cutting `join_concelho` — staging models can't supply it uniformly (different signals across portals + CAOP).

**Admin geography (CAOP-resolved)** — each staging model also exposes `geo_concelho_name`, `geo_parish_name`, `geo_key` via point-in-polygon against `dim_geography.freguesia_geom_pt`. CAOP-authoritative (INE/IGP polygons); the same-concelho dedup gate uses `COALESCE(geo_concelho_name, concelho)` so CAOP wins when geom resolves and portal-text is the fallback for NULL-geom devs. Practical impact (2026-06-06): unlocked 5 idealista cross-portal merges that the broken bronze `location_hierarchy` (separate task) would have left unjoinable indefinitely — including the user-reported "The Unique" idealista ↔ remax pair.

**Dual-signal Jaccard (2026-06-06 refactor)** — two parallel edge generators feed the link graph. Both gated on same-concelho; the UNION of their edges is what connected components sees.

- **Edge generator 1: token-Jaccard ≥ 0.6** on whitespace-split tokens of the clean_name. Catches subset/superset names ("jc barrocas" ⊆ "jc barrocas apartments" → 0.667). This was the original v1 signal.
- **Edge generator 2: char-trigram Jaccard ≥ 0.6** on the whitespace-stripped clean_name. Catches collapse variants ("vianova" ↔ "via nova" → 1.0) that the token signal is structurally blind to (token-Jaccard scores them at 0.0).

Why both, not one: char-trigrams handle whitespace collapse but regress subset matches ("jcbarrocas" vs "jcbarrocasapartments" trigram-Jaccard = 0.44, below 0.6). Tokens handle subsets but miss collapses. Either signal is sufficient evidence; both at ≥ 0.6 keeps false positives down.

Token-set ≥ 0.6 was deliberately picked for the bag-of-words layer because the distortions are *whole boilerplate words*, not character typos (Levenshtein fails on prefix insertions; Jaccard handles them naturally).

**No distance ceiling.** The original v1 had a 1km guardrail; it was dropped 2026-06-06. Empirical reality (from the imovirtual onboarding): portal pins disagree by **3–4km** on identical-named devs in the same concelho — worse than the original 200–300m audit. The 1km guard was vetoing correct merges (Ethula at 3,949m; JC Barrocas at 3,412m; UNIQUE Matosinhos at 4,697m). Same name + same concelho is sufficient evidence.

**Connected components** over the link graph give the final development grouping. A recursive CTE walks the undirected edges (plus self-loops so singletons get a component); each member's `dev_key` is the smallest `member_id` it can reach.

**Geometry hierarchy** — when a development has members on multiple portals, the unified geom + concelho + parish come from the highest-priority portal that has coordinates: **JLL > Zome > RE/MAX > imovirtual > idealista**. Locked 2026-05-22 (4-portal form); imovirtual added at slot 4 on 2026-06-06 (above idealista, below RE/MAX — see the 2026-06-06 addendum on [[2026-06-05-imovirtual-portal-onboarding]] for why the original "slot 2" was demoted). Reflects per-portal geo-quality trust (JLL = curated GPS with reliability flag; idealista = average of unit geocodes, last because the average smears for spread-out developments; imovirtual = typed dev-level pin + reverseGeocoding but coverage unverified at silver-build time, so the conservative slot wins for v1).

**Unit counts** — `portal_unit_counts` (JSONB) exposes every portal's reported `total_units` without picking an "authoritative" number. The portals report counts with heterogeneous semantics:

- idealista — *listed-units subset*, not the development total (2026-05-22 facade audit: "The Unique" listed as 3 units, facade shows ~50+).
- Zome — inventory (available + reserved + sold).
- JLL — `total_fractions`.
- RE/MAX — listings at RE/MAX (subset).
- imovirtual — TRUE project size (`number_of_units_in_project`). The only portal that distinguishes true total from listed subset; the listed count lives in the staging model's `raw_meta.listed_units_count` for consumers that want it.

Consumers read the breakdown and choose. The earlier Decision 9 (`total_units_authoritative = GREATEST(SCE count, MAX(portal))`) was retired when SCE matching was removed — there's no longer a reliable anchor to compute "authoritative" against.

**Why SCE is not merged here** — every attempt to match SCE buildings to portal developments produced low-confidence matches:

- Spatial proximity is noisy (Nominatim street-centroid SCE vs portal pins).
- No shared identifier — SCE has no project name; portals don't expose cadastral `matrix_article`.
- Street-address match works for idealista/JLL but not RE/MAX/Zome (which expose only parish + concelho).
- After stacking constraints (≥5 frações, ≤2.5y certs, no-idealista) the best Aveiro result was 4 of 11 portal-anchored devs matched, with the rest of the table dominated by promoted SCE-only rows that aren't "developments" in the marketed sense.

The reframe: SCE buildings and portal developments are different concepts. `silver_unified_developments` = marketed developments; [[silver_sce_buildings]] = certified buildings. `fn_assess_polygon` queries **both side-by-side** ("3 marketed developments + 26 certified buildings near here") rather than forcing them into one row.

**`geo_key` resolution** — point-in-polygon of the unified geom against `dim_geography.freguesia_geom_pt` via a `LATERAL ... LIMIT 1` (won't double-match). Authoritative INE/CAOP geography, no fuzzy text matching of portal concelho strings.

## See also

- [[dev-uid-stability]] — the append-only `silver_dev_uid_map` that gives the unified row a stable identifier for enrichment FKs (LLM dev-actor, CV).
- [[2026-06-09-silver-wall-clock-not-datasets]] — the orchestration decision that pairs with this concept (wall-clock daily silver, no Airflow Datasets).
- [[silver_sce_buildings]] — the sister table holding physical buildings with energy certificates; queried alongside, not merged.
- [[sce-buildings-clustering]] — the SCE-side equivalent concept (DBSCAN + fração-grain dedup).
- [[portal-field-map]] — the per-portal field-mapping reference that made Phase 1 normalization possible.
- [[idealista]], [[remax]], [[zome]], [[jll]], [[imovirtual]] — the five contributing portals.
- [[sprint-09]] — the sprint this shipped in (Slice B-prime).
