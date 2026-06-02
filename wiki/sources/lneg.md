---
title: LNEG — Geology & Hydrogeology
type: source
last_verified: 2026-06-02
tags: [gis, regulatory, government, geology, hydrogeology, arcgis-rest]
priority: P2
---

## For future Claude

This is a source page about LNEG (Laboratório Nacional de Energia e Geologia), narrowly scoped to the 1:500k geology layer (CGP500k) and the national aquifers layer. It documents the ArcGIS REST MapServer ingest with server-side reprojection, the deliberate scope at 1:500k due to higher-resolution gaps, and the self-signed SSL cert workaround. Read this page before editing [pipelines/gis/lneg/lneg_config.py](../../pipelines/gis/lneg/lneg_config.py).

## Source

- **Official name**: LNEG — Laboratório Nacional de Energia e Geologia
- **Owner**: government agency (national geological + energy laboratory)
- **Protocol**: ArcGIS REST MapServer (server-side reprojection to EPSG:3763)
- **Base endpoint pattern**: `https://sig.lneg.pt/server/rest/services/{CGP500k,RecursosHidro}/MapServer/2`
- **License**: open data
- **Schedule**: manual trigger

## Schema

Two bronze tables (both follow the generic-JSONB pattern: `feature_id INTEGER, layer_name VARCHAR, properties JSONB, geom GEOMETRY(GEOMETRY, 3763), _source_url TEXT, _load_timestamp TIMESTAMPTZ`):

- `bronze_geology.raw_lneg_geology_500k` — Geologia 1:500k, ~282 polygons national.
- `bronze_hydrology.raw_lneg_aquiferos` — Aquíferos (aquifer systems), ~63 polygons national.

Both: geometry = Polygon, EPSG:3763 (PT-TM06, server-reprojected).

**JSONB key authority** lives in the staging SQL files, not here ([[silver-dq-baseline]] Rule 0). LNEG publishes no machine-readable attribute spec — the live ArcGIS REST endpoint is the only ground truth. See:

- [`stg_lneg_geology.sql`](../../dbt/models/staging/geology/stg_lneg_geology.sql) — dated discovery comment + extractions for the CGP500k layer (current keys as of 2026-06-02: `Código`, `Descrição`, `Descrição1`, `Eonotema`, `Eratema`, `Sistema`, `Série`, `Zona`, `Intrusões_plutónicas`, `Intrusões_plutónicas1`, `OBJECTID`).
- [`stg_lneg_aquiferos.sql`](../../dbt/models/staging/hydrology/stg_lneg_aquiferos.sql) — dated discovery comment + extractions for the aquifers layer (current keys as of 2026-06-02: `CodigoInag`, `NomeCompleto`, `SistemaAquifero`, `Idade`, `IDUnidadeHidrogeologica`, `OBJECTID`).

**Important historical note (lesson learned 2026-06-02):** an earlier version of this page claimed `Idade_Litologia` as the geology key field. That was **never present** in the live ArcGIS data — the actual lithology code lives under `Código`, and chronostratigraphic context spreads across `Eonotema` / `Eratema` / `Sistema` / `Série` / `Zona` separately. The drift was caught when [silver_geo.geology](../../dbt/models/silver/geo/geology.sql) was first built against live bronze and the not_null test on `lithology_code` failed for 100% of rows. This is exactly the failure mode [[silver-dq-baseline]] Rule 0 (Schema discovery precedes derivation) exists to prevent.

## Silver layer

Shipped 2026-06-02 (sprint-09 WS4 quick-wins batch). Two siblings under [[silver_geo|silver/geo/]] — different schemas, different consumer semantics, no UNION.

- Aquifers: [dbt/models/staging/hydrology/stg_lneg_aquiferos.sql](../../dbt/models/staging/hydrology/stg_lneg_aquiferos.sql) + [dbt/models/silver/geo/aquifers.sql](../../dbt/models/silver/geo/aquifers.sql). Exposes raw bronze fields (`codigo_inag`, `aquifer_name`, `aquifer_system`, `aquifer_age`, `hydrogeo_unit_id`) + dual-CRS canonical naming.
- Geology: [dbt/models/staging/geology/stg_lneg_geology.sql](../../dbt/models/staging/geology/stg_lneg_geology.sql) + [dbt/models/silver/geo/geology.sql](../../dbt/models/silver/geo/geology.sql). Exposes `lithology_code` + descriptive `geological_era_code` (`LEFT(lithology_code, 1)`) parse only.
- Tests per [[silver-dq-baseline]].
- **NOT in dim_constraint_severity**: `fn_assess_polygon` reads these as contextual JSONB readout, NOT as regulatory gates. See [[medallion-layering]] for where silvers fit.

### Why no derived `aquifer_vulnerability` or `foundation_difficulty` in v1

Researched + dropped during sprint-09 WS4 planning (locked decision 17):

- **Aquifer vulnerability**: proper PT/international frameworks (DRASTIC, GOD, SINTACS) require depth-to-water + recharge + soil media + vadose-zone impact + conductivity — none of which are in this bronze. Deriving HIGH/MEDIUM/LOW from `Idade` (age) alone is not defensible because age ≠ confinement type. Sources: [DRASTIC application in Portugal — ResearchGate](https://www.researchgate.net/publication/26489074_Groundwater_vulnerability_assessment_in_Portugal); [DRASTICAI MDPI Portuguese case study](https://www.mdpi.com/2076-3263/11/6/228/htm).
- **Foundation difficulty**: PT regulation is Eurocode 7 (NP EN 1997) Geotechnical Categories — explicitly require site-specific CPT/SPT investigation; 1:500k era prefix is far too coarse. Worse, the **"Argilas de Aveiro" (Upper Cretaceous)** formation contradicts the obvious era-prefix CASE: it's smectite-rich, expandable, HIGH plasticity ([Galhano & Rocha, Clay Minerals, Cambridge Core](https://www.cambridge.org/core/journals/clay-minerals/article/abs/geostatistical-analysis-of-the-influence-of-textural-mineralogical-and-geochemical-parameters-on-the-geotechnical-behaviour-of-the-argilas-de-aveiro-formation-portugal/235F2F21E5A221E39DFE4E3873537440)) — flagging all `C` as MEDIUM is wrong for Aveiro. Era prefix isn't the signal; formation-specific clay mineralogy is.
- **Also**: DL 382/99 captação protection zones (the actual aquifer-related regulatory layer) are POINT-based protection perimeters around specific water-supply wells, NOT polygons over aquifer systems. We don't have that layer; LNEG's `Sistemas Aquíferos` shows extent, not protection.
- **v2 path**: either build a per-formation `dim_aveiro_formations` lookup keyed on `lithology_code` with per-row citations (HIGH for `C3` Argilas de Aveiro; HIGH for `Q1` Ria de Aveiro alluvium per [LTSER Ria de Aveiro / DEIMS-SDR](https://deims.org/dfc24538-730e-4e4b-9f04-8e84608b9999)), OR integrate DRASTIC inputs once [[lidar|LiDAR depth-to-water proxy]] + recharge rasters land.

### 1:50k raster (CGP50k JPGw) — sprint-10+ UX path

LNEG Geoportal publishes Folha 16-A (Aveiro, 1975), 16-C (Vagos), 13-D (Oliveira de Azeméis), 19-A/19-D (Cantanhede/Coimbra-Lousã), 22-B/22-D/23-A/23-C (Leiria region) as **georeferenced JPG (JPGw) rasters in PT-TM06/ETRS89**. Folhas 16-B (Águeda) and 16-D (Anadia) NOT yet published. Format is raster, NOT vector — can't feed `fn_assess_polygon`'s `ST_Intersects` directly. Sprint-10+ candidate paths: (a) load JPGws into MinIO + expose via WMS for the Atlas Inspector UI layer toggle; (b) manual outreach to `cartografia@lneg.pt` for internal vector data.

## Quirks

- **1:500k is the available resolution**: higher-resolution geology layers (CGP200k, CGP50k INSPIRE harmonised) have gaps:
  - **CGP200k**: Folha 5 (Beira Litoral, includes Aveiro) UNPUBLISHED. Cannot use.
  - **CGP50k INSPIRE**: 31,285 polygons total but only 30 of ~175 folhas published, ALL in northern PT. Aveiro is NOT covered.
  Hence, 500k is the only layer that gives PT-wide Aveiro coverage. When DGT publishes the missing folhas, revisit.
- **Self-signed SSL cert on sig.lneg.pt**: current workaround is `verify=False` in the requests session. **TODO** (Phase 7+ candidate): pin the cert to avoid silently accepting MITM on a regulatory data source. Until then, if you see `CertificateError`, that's the symptom of upstream rotating their cert.
- **PAGE_SIZE=1000, rate_limit=0.5s, request_timeout=180s**. Both layers are small (≤282 features) so a single request fetches each.
- **Lithology codes hierarchical**: the geology layer's `Idade_Litologia` field encodes age + composition in a structured code. Downstream silver-layer logic decodes the prefix (e.g., `C` = Cretácico era) for grouping.
- **Cross-source role**: geology + aquifers feed listing-feature engineering for "is this listing on stable bedrock?" (geology) and "what's the aquifer-recharge sensitivity here?" (aquifers, relevant for water-availability and pollution-risk assessments). [[srup-ogc]]'s aquíferos layer is a PROTECTED-zone subset of LNEG's national aquifers; the two are complementary (LNEG = "where are aquifers", SRUP = "which ones are protected").

## Last verified

2026-05-08 (Phase 3 PR 2 seed pass — config re-read).
