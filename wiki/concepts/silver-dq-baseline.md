---
title: Silver-layer data-quality baseline
type: concept
last_verified: 2026-06-02
tags: [dbt, silver, data-quality, conventions, sprint-09]
---

## For future Claude

This is a concept page about the data-quality rules every silver model in this warehouse must follow. It documents 4 universal invariants (dual-CRS, surrogate-key, row-count parity, FK denormalization integrity), what's deliberately NOT a rule (`accepted_values` on categorical columns — see Rationale section), and a "Statistical-source silver topology" mapping that says which silver answers which question. Read this before creating a new silver model, adding tests to an existing one, or wondering "should this column have an `accepted_values` test?"

## What it is

The minimum bar every `dbt/models/silver/**/*.sql` model meets. Operationalized via dbt YAML tests + pgTAP files at `tests/sql/silver_<model>_invariants.sql`. Established by sprint-09 WS4 quick-wins batch (APA + LNEG + INE silvers) and applied retroactively as silvers are touched.

## Why

Before sprint-09 WS4, silver-layer tests were ad-hoc per model (see [[silver_sce_buildings|sce-buildings-clustering]] + [[silver_unified_developments|cross-portal-dev-dedup]]). The 4 new silvers added at once (`floodplains`, `aquifers`, `geology`, `ine_indicators_long`) surfaced repeated patterns worth codifying so future Claude (or human) doesn't re-derive the same checks from scratch. The deliberate exclusion of `accepted_values` is the most load-bearing part of the page — without it, ad-hoc test writers default to enumerating values they happen to know about, which creates churn when upstream sources add new codes.

## How

### Rule 1 — Spatial dual-CRS invariant

Every spatial silver materializes BOTH columns per [[2026-05-10-dual-crs-storage]]:

- `geom GEOMETRY(<TYPE>, 4326)` — WGS84 for display, web maps, `ST_Within` predicates
- `geom_pt GEOMETRY(<TYPE>, 3763)` — PT-TM06 for distance + area in metres

Each gets a GIST index in a post-hook. dbt YAML enforces `not_null` + `dbt_utils.expression_is_true: ST_SRID(geom) = 4326` (and the symmetric 3763 check). pgTAP enforces `ST_IsValid` at runtime (dbt's expression_is_true is structural; pgTAP catches actual geometry corruption).

**Note**: SRUP siblings + `silver_geo/zoning.sql` + `silver_geo/census_demographics.sql` use the legacy `geom`(3763) + `geom_wgs84`(4326) drift naming. Sprint-10 cleanup ticket migrates them to canonical. New silvers follow canonical.

### Rule 2 — Surrogate-key invariant

Every silver with a `ROW_NUMBER()` PK enforces both `unique` AND `not_null` on the surrogate column in dbt YAML. The PK column name is `<model_singular>_key` (e.g. `floodplain_id`, `aquifer_key`, `geology_key`, `indicator_long_key`). Stable ordering in the ROW_NUMBER (e.g. `ORDER BY feature_id`, never random) so rebuilds produce reproducible IDs.

### Rule 3 — Bronze→silver row-count parity

For non-aggregating silvers, a pgTAP assertion: silver row count equals bronze row count filtered by whatever the staging-layer guard applies. Typically:

- Spatial: `silver_count = (SELECT COUNT(*) FROM bronze WHERE geom IS NOT NULL)`
- INE: `silver_count = (SELECT COUNT(*) FROM bronze_ine.raw_indicators WHERE valor IS NOT NULL)` (the staging filter)

For aggregating silvers (e.g. [[silver_sce_buildings|sce-buildings-clustering]] which DBSCAN-clusters), the parity test is `silver_count <= bronze_count` plus a sum-conservation check on aggregated fields (e.g. `frac_count`).

### Rule 4 — Foreign-key denormalization integrity

When a silver LEFT JOINs to a dim table and denormalizes a column (e.g. `floodplains.severity` from [[dim_constraint_severity|srup-constraint-model]]), add a `not_null` test on the denormalized column in dbt YAML + a pgTAP assertion (`COUNT(*) WHERE denorm_col IS NULL = 0`). Catches FK miss after the JOIN — the denormalization fails silently otherwise.

### NOT a rule — `accepted_values` on categorical columns

**Deliberately excluded.** Both upstream-bronze pass-through values AND silver-derived CASE outputs.

**Why**: we don't have full picture of upstream value sets at any given point. Blocking CI on unexpected values creates two failure modes:
1. **Churn**: upstream adds a new code → CI breaks → someone updates the test → cycle repeats per source.
2. **Silent suppression**: developer hits the failing test, adds the new value mechanically to make CI green, doesn't actually evaluate whether the new code matters semantically.

**Instead**: where a column has a known closed set (e.g. `geo_level`), the silver CASE includes an explicit `'unknown'` catch-all. Post-build sanity is via ad-hoc `SELECT col, COUNT(*) GROUP BY 1` queries (visible-but-non-blocking signal), not a hard test.

This convention is younger than [[silver_unified_developments|cross-portal-dev-dedup]]'s `accepted_values` tests on `geo_level` — those are grandfathered; sprint-10 cleanup can revisit.

## Per-silver checklist

When creating a new silver model, ensure:

- [ ] PK column named `<model_singular>_key`, ROW_NUMBER with stable ORDER BY, `unique` + `not_null` in YAML (Rule 2)
- [ ] If spatial: `geom` (4326) + `geom_pt` (3763), GIST post-hooks on both, `dbt_utils.expression_is_true` SRID tests in YAML (Rule 1)
- [ ] If spatial: pgTAP `ST_IsValid` + `ST_SRID` assertions in `tests/sql/silver_<model>_invariants.sql` (Rule 1 runtime check)
- [ ] pgTAP row-count parity assertion vs bronze (Rule 3)
- [ ] If LEFT JOIN to dim with denormalized column: `not_null` test on denormalized column + pgTAP `COUNT(*) WHERE col IS NULL = 0` (Rule 4)
- [ ] Cross-link `[[silver-dq-baseline]]` from the silver's YAML model description
- [ ] NO `accepted_values` tests added (intentional)

## Statistical-source silver topology

Two silvers handle statistical/timeseries data. They serve different questions and shouldn't be confused or merged:

| Silver | Sources | Geo granularity | Use case |
|---|---|---|---|
| [silver_market.macro_timeseries](../../dbt/models/silver/market/macro_timeseries.sql) | [[bpstat]] + [[ecb]] + [[eurostat]] | National PT / Eurozone / ISO country | Market-context: interest rates (Euribor + PT mortgage), housing-credit volumes, EU-aligned HPI. Pre-computed MoM/QoQ/YoY change rates. |
| [silver_market.ine_indicators_long](../../dbt/models/silver/market/ine_indicators_long.sql) | [[ine]] only | PT NUTS I/II/III + concelho + freguesia | Parish/concelho demand signals: employment %, foreign-nationality %, building stock aging, transaction counts per geography. Multi-dim (sex × age × category). |

**Overlap**: HPI is in both — INE 0009201 = PT-native quarterly methodology; Eurostat PRC_HPI_Q (in macro_timeseries) = EU-aligned methodology. Intentional — different consumers want different aggregations. See [[ine]] §Cross-source role.

**Why kept separate** (locked sprint-09 WS4 decision 16): merging would force lowest-common-denominator schema — dropping INE's freguesia/concelho granularity (the whole point for `fn_assess_polygon`'s "DADOS DO LOCAL" panel) OR widening macro_timeseries with NULLed-out columns nobody uses. Two silvers is the right shape.

**Rule for fn_assess_polygon authors**: when surfacing "what's the macro context here?" (interest rates, EU HPI) → query macro_timeseries. When surfacing "what's this neighbourhood like?" (employment, demographics, transactions at parish level) → query ine_indicators_long. Don't reach across.

## See also

- [[medallion-layering]] — where silver sits in the bronze→silver→gold stack
- [[2026-05-10-dual-crs-storage]] — the ADR Rule 1 enforces
- [[bronze-permissive]] — bronze accepts whatever; silver is where validation happens
- [[srup-constraint-model]] — example of Rule 4 in practice (dim_constraint_severity)
- [[sce-buildings-clustering]] — example of aggregating silver where Rule 3 morphs into `<=` + sum-conservation
- [[cross-portal-dev-dedup]] — example of aggregating silver with phase 1 invariants test
- [[apa]], [[lneg]], [[ine]] — the sources whose v1 silvers established this baseline
