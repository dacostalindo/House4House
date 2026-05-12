---
title: Ingest flows — six-flow taxonomy
type: concept
last_verified: 2026-05-12
tags: [ingest, flows, architecture, medallion, taxonomy]
---

## For future Claude

This is a concept page about the six-flow ingest taxonomy that classifies every data source in the warehouse by its ingest pattern. It explains the original four flows from the dev-tooling design (REST / scraping / GIS / derived) plus the two later additions (E for UC-3 spatial analysis, F for UC-2 competitive intel) that emerged from operational needs. Read this when adding a new source (pick the flow it fits, reuse the template), routing a question about "where does X happen" (flow tells you which medallion tier owns the work), or scoping a new use case (E and F show how flows compose).

## What it is

Six distinct ingest patterns. Each pattern has its own template, schedule shape, and bronze→silver→gold trajectory:

| Flow | Source class | Examples | Schedule |
|---|---|---|---|
| **A** | REST API | [[ine]], [[bpstat]], [[eurostat]], [[ecb]], [[idealista]] (RE API leg) | scheduled (monthly / quarterly) |
| **B** | Web scraping | [[idealista]] (Universal Scraper leg), [[sce]], future portal scrapers | scheduled (daily / weekly) |
| **C** | GIS bulk download / OGC API | [[caop]], [[bupi]], [[cadastro]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[apa]], [[bgri]], [[lneg]], [[lidar]], [[osm]], [[aveiro-pmot]] | manual / triggered |
| **D** | Derived computation | location scores, hedonic valuations, investment opportunities | post-ingestion dbt run |
| **E** | Spatial analysis composition | [[UC-3]] land opportunities | post-ingestion |
| **F** | Development portal cross-reference | [[UC-2]] competitive intel; [[remax]] / [[zome]] / [[jll]] developments | scheduled (weekly) |

A and B are the "pull from outside" flows; C is the bulk-file analogue for spatial data; D-F are the "compute over what we already have" flows that depend on A-C results being current.

## Why

**Why a taxonomy at all:** without one, every new source decision becomes "design from scratch." The taxonomy compresses the design space: pick a flow → reuse the template at `pipelines/{api,scraping,gis}/template/` → focus design effort on the source-specific quirks documented in the corresponding source page.

**Why six flows, not four:** the original dev-tooling design ([[2026-05-05-uv-workspace-shape]]'s sibling design doc) named A-D — REST / scraping / GIS / derived. Flows E and F emerged later as use cases firmed up:

- **E** (spatial composition) is structurally distinct from D (single-source derivation): it composes 4-5 spatial bronze layers with explicit CRS alignment (EPSG:3763) before the derived computation runs. Treating it as "just dbt" loses the CRS-alignment-is-load-bearing fact and the ST_ClusterDBSCAN parcel-grouping primitive.
- **F** (development portal cross-reference) is structurally distinct from B (web scraping): the deduplication and attribute-priority logic across multiple portals (RE/MAX > ERA > KW > C21) is the load-bearing work, not the per-portal scrape itself. Treating it as "B plus a join" loses the dev-portal-specific machinery (development_key MD5 hashing, SCE cross-reference, Idealista render routing).

Each flow has its own template + bronze schema + silver-layer convention. The cost of "one more flow" is one more template + a few wiki entries — small relative to clarity gained.

## How

### Flow A — REST API

```
Airflow DAG (scheduled)
  → Python operator (requests / pandasdmx)
    → API response (JSON / CSV / SDMX / JSON-stat)
      → Validate response schema (per [[bronze-permissive]] = freeze on type, evolve on columns)
        → Insert into bronze.raw_<source> (append-only)
          → dbt staging (type casts, null handling, [[pydantic-not-in-dlt]])
            → dbt silver (conform to dimensions)
              → dbt gold (metrics + facts)
```

Source pages: [[ine]], [[bpstat]], [[eurostat]], [[ecb]]. [[idealista]]'s RE API leg uses this shape for unit detail; the discovery leg uses Flow B.

### Flow B — Web scraping

```
Airflow DAG (scheduled)
  → Scrapy / Selenium / nodriver / ZenRows operator
    → Raw HTML pages
      → Store HTML snapshot in MinIO (s3://raw/<source>/<date>/...)
        → Parse HTML → structured records
          → Insert into bronze.raw_<source>
            → Geocode addresses via Nominatim (companion service, see [[osm]])
              → dbt silver (deduplicate, conform)
                → dbt gold
```

Source pages: [[idealista]] (Universal Scraper for development list + detail HTML), [[sce]] (only nodriver scraper in stack — Cloudflare Turnstile). The MinIO HTML-snapshot step is the audit trail for [[bronze-permissive]] — even if our parser is wrong, we have the raw HTML to reparse.

### Flow C — GIS bulk download / OGC API

```
Airflow DAG (manual or triggered)
  → Download file (wget / curl) OR paginate OGC API
    → Store raw file in MinIO (s3://raw/<source>/<version>/...)
      → Import via ogr2ogr / osm2pgsql into bronze_<domain>.raw_<source>
        → dbt silver (reproject to EPSG:3763 if needed, clean, index)
          → Spatial joins for enrichment in gold
```

Source pages: 14 GIS sources — [[caop]], [[bgri]], [[bupi]], [[cadastro]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[apa]], [[lneg]], [[lidar]], [[osm]], [[aveiro-pmot]].

Sub-pattern: **WFS** (legacy [[crus]] + [[srup]]) vs **OGC API Features** (modern [[crus-ogc]] + [[srup-ogc]]). OGC API is the strategic future; WFS dual-runs during parity validation, then decommissions. Both share the bulk-download scaffolding via `pipelines/gis/template/`.

### Flow D — Derived computation

```
Airflow DAG (post-ingestion)
  → dbt run
    → silver_properties.unified_listings
    + silver_location.* (transport, schools, healthcare, POIs)
      → Spatial proximity queries (PostGIS ST_DWithin)
        → gold_analytics.property_location_scores
          → gold_analytics.hedonic_features
            → Python / SQL hedonic model scoring
              → gold_analytics.property_valuation
                → gold_reporting.investment_opportunities
```

No external source. Pure transformation over current bronze + silver. Per [[medallion-layering]], this is gold-layer work — the silver tables are inputs, gold tables are the output. Use cases: hedonic valuation feeding [[UC-1]] investment opportunities + [[UC-2]] pricing strategy.

### Flow E — Spatial analysis composition (UC-3)

```
[[cos]] (land use) + [[crus]]/[[crus-ogc]] (zoning) + [[srup]]/[[srup-ogc]] (constraints) + [[bupi]] (parcels) + Building Footprints
  → stg_* (staging views — CRS alignment to EPSG:3763)
    → silver_geo.parcel_buildability (pre-filtered to CRUS municipality extents)
      → ST_ClusterDBSCAN (parcel contiguity grouping)
        → gold_analytics.development_sites (opportunity scoring)
        → gold_analytics.site_parcels (parcel-to-site mapping)
```

**CRS alignment** is load-bearing here:
- [[bupi]], [[cos]], [[crus]] / [[crus-ogc]], [[cadastro]] are native EPSG:3763 → no transform.
- [[srup]] IC / RAN / DPH and Building Footprints are EPSG:4326 → `ST_Transform` to 3763 at staging.
- All spatial joins in EPSG:3763 (projected, metres — accurate area / distance).

Use case: [[UC-3]] Land Development Opportunity Detection. The flow composes 5+ spatial bronze layers, each with its own CRS, and the alignment step is where bugs hide. Treating it as Flow D would lose this discipline.

### Flow F — Development portal cross-reference (UC-2)

```
Portal APIs (RE/MAX, ERA, C21, KW) → Python requests/sessions
  → Raw JSON responses
    → Store JSONL in MinIO (s3://raw/<portal>_developments/<YYYYMMDD>/)
      → Insert into bronze_listings.raw_<portal>_developments
        → dbt staging (stg_<portal>_developments, stg_<portal>_units)

Idealista render routing:
  stg_idealista WHERE cv_is_render = TRUE
    → Excluded from resale_listings (is_new_development_combined = FALSE only)
    → Routed to development_units (matched to development by GPS proximity)
    → Brings Idealista unit-level pricing into competitive_developments

Combined silver:
  Portal staging + Idealista renders + [[sce]] cross-reference
    → silver_properties.competitive_developments (unified, deduped, one row per dev)
    → silver_properties.development_units (unit-level detail from all sources)
    → silver_properties.development_source_xref (portal cross-reference)
      → gold_analytics.development_lifecycle (timeline)
      → gold_analytics.absorption_rate_model (sell-through)
      → gold_analytics.fact_all_listings (UNION: resale_listings + development_units)
```

**Dedup strategy:**
- Primary: `development_key = MD5(name_normalized + ROUND(lat, 3) + ROUND(lng, 3))`
- Secondary: `ST_DWithin(geom_pt, 200m)` + `pg_trgm similarity(name) > 0.4`
- [[sce]] cross-reference: LEFT JOIN on freguesia_code + GPS proximity + address similarity
- [[idealista]] fallback: `ST_ClusterDBSCAN` on `is_new_development_combined` listings not matched to any portal

**Attribute priority** (when portals disagree, ranked by observed coverage):
- GPS: ERA > RE/MAX > KW > C21
- Price: ERA (93%) > KW (72%) > RE/MAX (62%) > C21 (1%)
- Unit count: [[sce]] ground truth > ERA (100%) > RE/MAX (96%) > C21 (94% via floor plans)
- Status: ERA (Available / Reserved / Sold) > RE/MAX (isSold) > KW (construction phase)
- Timeline: KW (fund_date + completion_date) > [[sce]] (PCE dates)

Use case: [[UC-2]] New Housing Unit Pricing Strategy. The portal mix gives breadth; the cross-reference + dedup gives confidence; the attribute-priority ranking handles the conflicts. Treating it as Flow B + a dbt join would lose the priority-table machinery and the [[sce]] ground-truth join.

## Adding a new source — picking the flow

1. **Source returns structured JSON / CSV / SDMX from a REST API**: Flow A. Use `pipelines/api/template/`.
2. **Source returns HTML you have to parse**: Flow B. Use `pipelines/scraping/template/`. Add MinIO snapshot per [[bronze-permissive]].
3. **Source is a bulk file (GeoPackage / Shapefile / TIFF) or an OGC-API spatial endpoint**: Flow C. Use `pipelines/gis/template/`.
4. **Source is "compute X from current bronze + silver"**: Flow D. Pure dbt. No new ingest pipeline.
5. **Source is a multi-layer spatial composition with CRS alignment**: Flow E. Lives downstream of multiple Flow C results.
6. **Source is a multi-portal cross-reference with dedup logic**: Flow F. Composes Flow A or B per portal, plus a dedup silver layer.

If a new source doesn't fit any of these — that's a signal to consider Flow G + add it here. Don't shoehorn into a wrong flow; the templates encode load-bearing assumptions.

## See also

- [[medallion-layering]] — the bronze/silver/gold framing this taxonomy operates within
- [[bronze-permissive]] — the bronze policy applied uniformly across A, B, C, F
- [[pydantic-not-in-dlt]] — the Pydantic guardrail (configs yes, ingest no)
- [[scd2-row-hash]] + [[heartbeat-sidecar]] — applied to portal sources in Flow A/B/F
- [[zenrows-universal-vs-re-api]] + [[payload-cache-lifecycle]] — [[idealista]]'s mixed Flow A + Flow B pattern
- [[UC-1]], [[UC-2]], [[UC-3]] — the use cases that pull on Flows D, F, E respectively
- All 23 source pages in [[index]] grouped under "Sources"
- [README.md §6](../../README.md) — the canonical source for this taxonomy
