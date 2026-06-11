---
title: GesEdu — Rede Escolar (national school register, ArcGIS REST)
type: source
last_verified: 2026-06-06
tags: [gis, education, amenity, government, arcgis-rest]
priority: P1
---

## For future Claude

This is a source page about **GesEdu / Rede Escolar** — the authoritative national register of every Portuguese school (pré-escolar → secundário + profissional, public + private), used as a **geo-amenity layer** for listings (proximity-to-schools). It is owned by **AGSE, I.P.** (Agência para a Gestão do Sistema Educativo; created by DL 99/2025, absorbed DGEstE/DGAE/IGeFE).

The key finding (verified 2026-06-06): GesEdu's `PesquisaRede` map is backed by a **public ArcGIS REST FeatureServer** that returns código + agrupamento + street address + **native lat/lon** in one paginated JSON pull — so this needs **no UI scrape and no geocoding**. Pair with [[infoescolas]] (quality, código-joined) and [[bgri]] (resident attainment). Design doc: [[pt-education-amenity-design]]. Build template: [[crus-ogc]] (same `ArcgisRestAdapter` path). Read this before editing `pipelines/gis/gesedu/`.

## Source

- **Official name**: Rede Escolar (Roteiro das Escolas), surfaced via the GesEdu `PesquisaRede` map
- **Owner**: government agency (AGSE, I.P. — `agse.pt`; ArcGIS Online org `pXkWEYl9JkoX4UHe`, owner `agse.esri`)
- **Protocol**: ArcGIS REST Feature API (paginated GeoJSON) — `protocol="arcgis_rest"` in the unified template
- **Base endpoint**: `https://services-eu1.arcgis.com/pXkWEYl9JkoX4UHe/arcgis/rest/services/RedeEscolar_mapa/FeatureServer/0/query`
- **License**: none stated (undocumented public API) — treat as internal-derived, do not redistribute raw
- **Schedule**: manual trigger (register changes slowly; refresh per school year)
- **Coverage**: national, ~8,670 schools, all levels + tutelas

## Schema

Bronze table: `bronze_location.raw_gesedu_schools` (amenity layer, same domain as [[osm]] POIs).

Typed columns direct from FeatureServer `outFields=*` (no JSONB unpacking):
- `codescme` — código de escola DGEEC (6-digit) — **the join key to [[infoescolas]] (`Código Escola DGEEC`)**
- `dgeec` — DGEEC code (cross-check)
- `coduome` / `nomeuo` — agrupamento / unidade orgânica code + name
- `nome` — school name
- `morada` / `cp4` / `cp3` / `localidade` / `concelho` / `distrito` — address parts
- `tipologia` / `ciclo` / `ensinos_min` — typology + ensino levels (drives the secundário "scored vs unscored" split)
- `situacao_escola` — filter to "Em funcionamento"
- `tutela` — public/private
- `geom` GEOMETRY(POINT, 4326) + `geom_pt` GEOMETRY(POINT, 3763) per [[2026-05-10-dual-crs-storage]]

## Build scope (v1) — scoped against repo patterns

Mirror [[crus-ogc]] exactly; the unified template already has the adapter, so this is config + two thin DAGs, **no new fetch code**:

1. `pipelines/gis/gesedu/gesedu_config.py` — Pydantic config (cf. `crus_ogc_config.py`): `ENDPOINT_URL` = FeatureServer `/query`, `protocol="arcgis_rest"`, `PAGE_SIZE=2000` (server `maxRecordCount`), `bronze_schema_table="bronze_location.raw_gesedu_schools"`, `minio_prefix="gesedu"`.
2. `gesedu_ingestion_dag.py` — `ArcgisRestAdapter` (already in `pipelines/gis/template/ingestion_template.py`) → `probe()` then `fetch_to_minio` GeoJSON at `raw/gesedu/{YYYYMMDD}/schools.geojson`. ~5 pages.
3. `gesedu_bronze_dag.py` — `ijson`-streaming loader (cf. crus_ogc, BATCH_SIZE≈20) → typed DDL above, `geom = ST_SetSRID(ST_GeomFromGeoJSON(...),4326)` + `geom_pt = ST_Transform(geom,3763)`, GIST index on both. Filter `situacao_escola='Em funcionamento'`.
4. dbt: declare bronze table in `dbt/models/staging/location/_staging_location__sources.yml` (cf. the `raw_osm_pois` block); `stg_gesedu_schools.sql` via `/stg-from-bronze` (NULL guards, `not_null` on `codescme`+`geom`).
5. Surfacing mart (gold): catchment per listing — `ST_DWithin(listing.geom_pt, school.geom_pt, {1000,3000})` (metric, EPSG:3763 per [[2026-05-10-dual-crs-storage]] — supersedes the design doc's "geography" note to match repo convention). Two buckets: coverage (any school) + quality (secundário-with-score, joined to [[infoescolas]]).

## Quirks

- **Undocumented public API** — no published terms, AGSE-hosted ArcGIS Online (EU1). Be polite (rate-limit), request `outSR=4326`, and add a liveness/redirect check; do NOT hardcode the `services-eu1` host blindly (reorg drift risk — see below).
- **No geocoding needed** — geometry ships native, which is why the design abandoned the GesEdu-scrape + [[2026-05-10-nominatim-osrm-self-hosted|Nominatim]] geocode path. Nominatim is a fallback only for any null-geometry residual.
- **Reorg/URL-drift (Gate 6, 2026-06-06)**: AGSE (DL 99/2025) now owns GesEdu; DGEstE/DGAE/IGeFE extinct. The FeatureServer survived under AGSE but governance changed — treat the endpoint as drift-prone over 1–2 yrs.
- **código grain**: `codescme` = establishment; `coduome` = agrupamento. [[infoescolas]] exposes both, so join at either grain. v1 joins per-escola on `codescme`.

## Last verified

2026-06-06 — FeatureServer probed live (8,670 features, fields + geometry confirmed via direct `/query` call); endpoint + field map saved to the project memory. Not yet built — this is the scoped spec.
