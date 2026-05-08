---
title: Medallion layering (bronze / silver / gold)
type: concept
last_verified: 2026-05-08
tags: [medallion, dbt, schema, architecture, dlt]
---

## For future Claude

This is a concept page about the medallion architecture (bronze/silver/gold) as implemented in House4House. It explains the per-source bronze schemas, the silver "conformed" layer organized by domain (not by source), the gold analytical schemas, and where each transformation belongs (dlt = bronze; dbt staging = bronze→silver; dbt marts = silver→gold). Read this when adding a new source, deciding which schema a new table belongs in, or being asked "should this column be at silver or gold?"

## What it is

House4House follows the medallion architecture with three layers (plus a metadata schema):

```
External Source → Ingestion (pipelines/) → MinIO raw
                                        ↓
                                     Bronze (PostGIS) — per-source schemas
                                        ↓
                                     Silver (dbt) — conformed by domain
                                        ↓
                                     Gold (dbt) — analytics + reporting
```

The schemas are created by [warehouse/init/001_create_schemas.sql](../../warehouse/init/001_create_schemas.sql) on first container start.

## Why

**Why three layers** (not "just dbt on the raw tables"):

1. **Bronze isolates upstream drift.** Per [[bronze-permissive]], bronze accepts whatever the source returns, including regressions. If silver/gold built directly on the raw API response, every upstream change would force schema migrations across the analytical layer. Bronze absorbs the drift.

2. **Silver lets us conform across sources.** Listings come from [[idealista]], [[jll]], [[remax]], [[zome]] with different column names, types, and conventions. Silver normalizes to a unified "PT residential listing" shape. Without silver, gold queries would be filled with `COALESCE(idealista.price, jll.preco_pedido, remax.listing_price, zome.precoimovel)`.

3. **Gold gives analytical models room to breathe.** Aggregations, denormalizations for BI tools, derived KPIs. Cheap to recompute from silver; never the source of truth.

**Why per-source bronze schemas** (not one big `bronze`): governance and blast radius. Each source has its own schema (`bronze_listings`, `bronze_regulatory`, `bronze_geology`, etc.). Cross-source contamination is impossible at the SQL level. dbt source declarations live in `dbt/models/staging/<domain>/_staging_<domain>__sources.yml` and reference the bronze schemas explicitly.

## How

**The actual schema map** (from `warehouse/init/001_create_schemas.sql`):

**Bronze (per-source, raw):**

- `bronze_listings` — [[idealista]], [[jll]], [[remax]], [[zome]] (portals + scrapers)
- `bronze_regulatory` — [[caop]], [[bupi]], [[cadastro]], [[cos]], [[crus]], [[crus-ogc]], [[srup]], [[srup-ogc]], [[sce]]
- `bronze_geo` — administrative + general geography (some [[caop]]-derivative tables land here)
- `bronze_macro` — [[ecb]], [[bpstat]], [[eurostat]] (financial / macro indicators)
- `bronze_ine` — [[ine]] (statistics)
- `bronze_terrain` — [[lidar]] (DTM / DSM manifest tables)
- `bronze_geology` — [[lneg]] geology layer
- `bronze_hydrology` — [[apa]] floodplain, [[lneg]] aquifers
- `bronze_location` — geocoding caches, location-resolution intermediates
- `bronze_tourism` — tourism-specific feeds

**Silver (conformed, by domain):**

- `silver_properties` — unified residential listing model (across all 4 portals)
- `silver_geo` — clean administrative + boundary entities
- `silver_location` — POI / routing / geocoded entities
- `silver_market` — market aggregates, transaction data, price indices
- `silver_ref` — reference / dimension lookups

**Gold (analytical):**

- `gold_analytics` — facts + dimensions feeding analytical workloads
- `gold_reporting` — denormalized models for BI tools / dashboards

**Metadata:**

- `metadata` — dbt-managed run metadata, lint-output state, etc.

**Where transformations belong:**

| Transformation | Where | Example |
|---|---|---|
| Source-faithful capture (no judgment) | Bronze (dlt) | `bronze_listings.raw_idealista` |
| Type casts, NULL guards, field renames | Silver staging (dbt `stg_*.sql`) | `silver_properties.stg_idealista_listings` |
| Cross-source unification | Silver intermediates / marts | `silver_properties.unified_listings` |
| Aggregations, KPI denormalization | Gold | `gold_analytics.fct_listings_monthly` |
| Validation tests | dbt-utils on staging + silver | column-not-null, accepted-values, range |

**Source YAML conventions**: each `dbt/models/staging/<domain>/_staging_<domain>__sources.yml` declares its bronze sources. Naming: `_staging_<domain>__sources.yml` (note the double underscore). See [[staging-yaml-conventions]] (TODO — concept page captures this).

**MinIO landing-zone convention**: `s3://raw/{source}/{version}/{filename}` with audit copy stored per run. No overwrites — the audit layer sits BEFORE bronze and is the genuine ground truth if bronze gets corrupted.

**Bronze loading deferred from raw**: when a brand-new source arrives, raw data is explored first (in MinIO) before the bronze loader DAG is built. Schema confirmed, then bronze loaded. Avoids "we built a bronze table for a payload shape that turned out wrong."

## See also

- [[bronze-permissive]] — the policy that defines what bronze accepts
- [[pydantic-not-in-dlt]] — the strict corollary on validation placement
- [[scd2-row-hash]] — the SCD2 versioning used inside bronze for portals
- [[heartbeat-sidecar]] — the staleness signal that complements SCD2 in bronze
- All 23 sources/ pages — every source's bronze table mapping references this layout
- [warehouse/init/001_create_schemas.sql](../../warehouse/init/001_create_schemas.sql) — the source-of-truth schema definitions
