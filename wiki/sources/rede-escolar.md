---
title: GesEdu Rede Escolar — PT School Register (point geometry)
type: source
last_verified: 2026-06-06
tags: [education, schools, arcgis, geo, gesedu, agse, p1]
priority: P1
---

## For future Claude

This note is a source page about GesEdu's `RedeEscolar_mapa` ArcGIS REST FeatureServer — the
canonical PT school register with point geometry, owned by AGSE I.P. since the 2025 reorg.
It is the master location layer for the education amenity pillar; every other education source
([[publico-rankings]], [[infoescolas]], [[dges-acesso]], [[dgeec-ens-sup]]) joins back to a
school in this register via `codigo_escola` (CODESCME). Read this page before editing
[pipelines/gis/rede_escolar/rede_escolar_config.py](../../pipelines/gis/rede_escolar/rede_escolar_config.py) —
it documents the pagination strategy, the AGSE reorg drift risk, and why this skipped the
`pipelines/gis/template/` GIS template in favor of a custom paginated DAG (same justification
shape as [[publico-rankings]]).

## Source

- **Official name**: Rede Escolar — Sistema de Informação da Educação (GesEdu)
- **Owner**: AGSE I.P. (Administração-Geral do Sistema Educativo, DL 99/2025) — absorbed
  DGEstE / DGAE / IGeFE. ArcGIS Online tenant `pXkWEYl9JkoX4UHe` owner `agse.esri`.
- **Protocol**: anonymous HTTPS GET against an ArcGIS REST FeatureServer query endpoint.
  Pagination via `resultOffset` + `resultRecordCount` (server cap `maxRecordCount=2000`).
- **Base endpoint**:
  `https://services-eu1.arcgis.com/pXkWEYl9JkoX4UHe/arcgis/rest/services/RedeEscolar_mapa/FeatureServer/0/query`
- **Live count probe**: append `?where=1=1&returnCountOnly=true&f=json`. Returns 8,670 features
  (verified 2026-06-06).
- **License**: undocumented public API. Treat the raw blobs as internally-derived per the
  same caution applied to [[infoescolas]]; do not redistribute.

### Sibling layers (NOT ingested here)

- `RedeEscolar_tab` — tabular variant (no geometry). Dropped.
- `UnidadesOrganicas_mapa` + `UnidadesOrganicas_tab` — agrupamento-grain layers. Considered
  for join enrichment in silver; bronze stays per-school.

## Schema

42 fields per feature. Renamed to readable Portuguese at bronze per
[[dbt-source-column-descriptions]]. Highlights:

| Source key | Renamed column | Notes |
| --- | --- | --- |
| `CODESCME` | `codigo_escola` | PK. DGEEC 6-digit code. Joins to `publico_rankings.id_publico` (sometimes) and `infoescolas`. |
| `CODUOME` / `NOMEUO` | `codigo_uo` / `nome_uo` | Agrupamento. Joins to `publico_rankings.codigo_uo_dgeec`. |
| `NOME` | `nome` | School name. |
| `LATITUDE` / `LONGITUDE` | `latitude` / `longitude` | Redundant with `geom.y/x` but kept for spot-check. |
| `geometry.coordinates` (GeoJSON) | `geom` (4326) + `geom_pt` (3763) | Dual-CRS per [[2026-05-10-dual-crs-storage]]. |
| `TIPOLOGIA` | `tipologia` | e.g. `EB1`, `EB2,3/S`, `JI`, `Sec`. |
| `SITUACAOESCOLA` | `situacao_escola` | Silver filters `= 'Em funcionamento'`. |
| `NATUREZAINSTITUCIONAL_DESC` | `natureza_institucional_desc` | `Pública` vs `Privada`. |
| `DGEEC` | `dgeec_code` | Often duplicates `CODESCME` but kept separate for drift diagnostic. |

Full column descriptions live in
[`dbt/models/staging/education/_staging_education__sources.yml`](../../dbt/models/staging/education/_staging_education__sources.yml).

### Bronze DDL preview

```sql
CREATE TABLE bronze_education.raw_rede_escolar (
  run_date         date        NOT NULL,
  codigo_escola    text        NOT NULL,
  source_loaded_at timestamptz NOT NULL DEFAULT now(),
  arcgis_objectid  bigint,
  codigo_uo        text,
  nome_uo          text,
  nif_uo           text,
  nome             text,
  ...
  latitude         double precision,
  longitude        double precision,
  ...
  geom             geometry(Point, 4326),
  geom_pt          geometry(Point, 3763),
  PRIMARY KEY (run_date, codigo_escola)
);
```

### Pagination verification (2026-06-06)

```text
offset=0000: 2000 features  exceededTransferLimit=True   first OID=469921
offset=2000: 2000 features  exceededTransferLimit=True   first OID=471921
offset=4000: 2000 features  exceededTransferLimit=True   first OID=473921
offset=6000: 2000 features  exceededTransferLimit=True   first OID=475921
offset=8000:  670 features  exceededTransferLimit=None   first OID=477921
                          ─────
total                       8670 ✅
```

Page-size 2000 holds exactly on every non-tail page; OIDs are sequential and stable.
The bronze loader pre-computes offsets from the live count probe; the summary task
reconciles `sum(page_features) == probe_total` and fails the DAG on drift.

## Quirks

- **No SLA**. Undocumented public API. AGSE I.P. inherited GesEdu through DL 99/2025;
  the arcgis.com org id (`pXkWEYl9JkoX4UHe`) held through the reorg but the host or path
  can drift without notice. The ingestion DAG always runs the cheap `returnCountOnly` probe
  first — a probe failure fails fast before the fanout.
- **~14% of schools have NULL geometry** (verified 2026-06-06 on the tail page: 92/670).
  The loader retains those rows with `geom`/`geom_pt` NULL — better to know a school exists
  than to silently drop it. Silver filters them out for spatial queries.
- **`DGEEC` field duplicates `CODESCME`** in most rows but is kept separate. Acts as a
  drift sentinel: if the two diverge, the schema has changed.
- **`DTINICIO` is text, not date**. Source format is inconsistent (`"01-09-1990"`, `"1990"`,
  empty). Don't cast in bronze; silver normalizes if a downstream model needs it.
- **`SITUACAOESCOLA`** is the operational filter. The full register includes extinct,
  suspended, and "em construção" schools; silver promotes only `'Em funcionamento'`.
- **`maxRecordCount=2000` is a server cap, not a request param**. Trying `resultRecordCount=5000`
  silently returns 2000 with `exceededTransferLimit=True`. The DAG pins page size to 2000
  to match.
- **Monthly snapshots accumulate** under `raw/rede_escolar/{run_date}/`. The PK is
  `(run_date, codigo_escola)` — silver picks the latest run_date for current-state queries
  and can read the history for change-over-time facts (school openings/closings).

## DAGs

- `rede_escolar_ingestion` — paginated download, `@monthly`, fans out N pages from the live
  count probe, uploads to `s3://raw/rede_escolar/{run_date}/page_NNNNNN.geojson`.
- `rede_escolar_bronze_load` — discovers latest snapshot, parses GeoJSON pages, unnests
  with rename map + builds dual-CRS PostGIS geometry, upserts into
  `bronze_education.raw_rede_escolar`. Manual trigger.

Both live under `pipelines/gis/rede_escolar/`. Custom DAG shape (NOT the GIS template) —
same rationale as [[publico-rankings]]: the template handles single-URL file downloads,
not paginated REST query endpoints.

## Last verified

2026-06-06 — count probe returned 8,670; live field set matches the bronze rename map
exactly (zero drift); tail page produced unique CODESCMEs; 92/670 features had NULL geom
on the tail page sample.
