---
title: DGEEC Estabelecimentos do Ensino Superior — PT higher-ed register (shapefile)
type: source
last_verified: 2026-06-07
tags: [education, higher_ed, schools, geo, shapefile, dgeec, dgterritorio, snig, p1]
priority: P1
---

## For future Claude

Source page for DGEEC's `Estab_Ens_Sup_Portugal` shapefile — the canonical PT higher-education
register (universidades, politécnicos, militar/policial), distributed by DGTerritorio via
the SNIG ATOM feed under CC BY 4.0. This is source #3 of the 5-source PT education amenity
pillar; it covers the higher-ed slice that [[rede-escolar]] explicitly excludes
([[rede-escolar]] is the basic+secondário register, keyed at the per-school 6-digit grain).
Read this page before editing
[pipelines/gis/dgeec_ens_sup/](../../pipelines/gis/dgeec_ens_sup/) —
it documents the **two grain-of-source traps** the live probe exposed (DGEEC's misleading
"Estabelecimento" label and the 10-char DBF truncation that flattens accents), and why this
skipped the `pipelines/gis/template/` template despite §3.5 of the
[[pt-education-amenity-pillar]] planning doc claiming a clean fit.

## Source

- **Official name**: Estabelecimentos do Ensino Superior — Portugal
- **Owner**: DGEEC (Direção-Geral de Estatísticas da Educação e Ciência), distributed by
  DGTerritorio via the SNIG INSPIRE ATOM feed.
- **Protocol**: anonymous HTTPS GET of a single ZIP archive. URL has been stable across
  releases (no year/version in the path); DGEEC overwrites in place.
- **Download URL**:
  `http://geo2.dgterritorio.gov.pt/ATOM-download/DGEEC/Estab_Ens_Sup_Portugal.zip`
- **Live probe (2026-06-07)**: 40 788 bytes, valid ZIP, contains `.shp/.shx/.dbf/.prj/.cpg`
  + QGIS metadata (`.qix/.qmd`). Native EPSG:4326 (geographic, WGS84). Encoding UTF-8.
- **License**: CC BY 4.0 (per the SNIG ATOM index and the DGEEC catalogue entry).
- **Release date**: file mtimes inside the bundle are 2023-03-15. DGEEC publishes
  irregularly (years between releases).

## Why a custom DAG (not the template)

The GIS ingestion template at `pipelines/gis/template/gis_ingestion_template.py` auto-extracts
ZIPs to a single inner file matching `expected_format` and **deletes the ZIP**
([gis_ingestion_template.py:371](../../pipelines/gis/template/gis_ingestion_template.py)).
Shapefiles are bundles of 5+ sidecars (`.shp/.shx/.dbf/.prj/.cpg`); extracting only `.shp`
produces an unreadable file. No existing source in this repo actually uses
`expected_format='shp'` — every GIS source today uses `gpkg`. Templatising shapefile
bundles is a separate refactor, deferred until N≥2 sibling shapefile sources.

The custom ingestion DAG therefore mirrors the bypass shape used by [[rede-escolar]] and
[[publico-rankings]] — but for a different reason (multi-file bundle, not pagination).

## Schema (16 attribute fields + Point geometry)

Verified live 2026-06-07 via `pyogrio.read_info()`. **Two traps to be aware of:**

1. **Shapefile DBF truncates field names to 10 ASCII chars** — every column ships with a
   mangled label that loses accents and gets cut mid-word
   (`Código do` for `Código do Estabelecimento`, `Outro tele` for `Outro telefone`, etc.).
   The bronze loader keys off the truncated label and renames to readable snake_case.
2. **DGEEC's "Estabelecimento" here means the parent institution**, NOT a physical
   building. The shapefile has 321 rows = 321 Unidades Orgânicas
   (faculdade/escola/instituto); `Código do Estabelecimento` is **NON-UNIQUE** (101
   distinct values, e.g. all UOs of Universidade do Porto share `Código do Estabelecimento`).
   This is the opposite of [[rede-escolar]], where `codigo_escola` (CODESCME) is at the
   per-building 6-digit grain. The bronze rename map deliberately calls this column
   `codigo_instituicao` (not `codigo_estabelecimento`) to surface the confusion.

| DBF (10-char) | Full label | Bronze column | Type | Notes |
| --- | --- | --- | --- | --- |
| `Código do` | Código do Estabelecimento | `codigo_instituicao` | text | zfill(4); non-unique |
| `Estabeleci` | Estabelecimento | `instituicao_nome` | text | parent name |
| `Código da` | Código da Unidade Orgânica | `codigo_unidade_organica` | text | zfill(4); **PK** |
| `Unidade Or` | Unidade Orgânica | `unidade_organica_nome` | text | |
| `Natureza e` | Natureza e Tipo | `natureza_tipo` | text | 6 distinct values |
| `Website` | Website | `website` | text | |
| `Email` | Email | `email` | text | |
| `Morada` | Morada | `morada` | text | |
| `Código Po` | Código Postal | `codigo_postal` | text | `"9501-801 PONTA DELGADA"` |
| `Distrito` | Distrito | `distrito` | text | includes ilhas (`Ilha de São Miguel`) |
| `Concelho` | Concelho | `concelho` | text | |
| `Telefone` | Telefone | `telefone` | text | |
| `Outro tele` | Outro telefone | `outro_telefone` | text | |
| `Fax` | Fax | `fax` | text | often = telefone |
| `Latitude` | Latitude | `latitude` | double precision | redundant w/ geom.y |
| `Longitude` | Longitude | `longitude` | double precision | redundant w/ geom.x |
| geometry | (Point) | `geom` (4326) + `geom_pt` (3763) | geometry | dual-CRS per [[2026-05-10-dual-crs-storage]] |

Full column descriptions live in
[`dbt/models/staging/education/_staging_education__sources.yml`](../../dbt/models/staging/education/_staging_education__sources.yml).

### Bronze DDL preview

```sql
CREATE TABLE bronze_education.raw_dgeec_ens_sup (
  run_date                date        NOT NULL,
  source_loaded_at        timestamptz NOT NULL DEFAULT now(),
  codigo_instituicao      text,
  instituicao_nome        text,
  codigo_unidade_organica text,
  unidade_organica_nome   text,
  natureza_tipo           text,
  ...
  latitude                double precision,
  longitude               double precision,
  geom                    geometry(Point, 4326),
  geom_pt                 geometry(Point, 3763),
  PRIMARY KEY (run_date, codigo_unidade_organica)
);
```

### Live probe (2026-06-07)

```text
ZIP size               : 40 788 bytes
ZIP contents           : .cpg .dbf .prj .qix .qmd .shp .shx
Layer name             : Estab_Ens_Sup_Portugal
Geometry type          : Point
CRS                    : EPSG:4326 (.prj: GCS_WGS_1984, .cpg: UTF-8)
Features               : 321
Field count            : 16 (planning §3.5 said 14 — `Outro telefone` + `Fax` missed)
Unique codigo_uo       : 321 / 321  ✅ (PK candidate)
Unique codigo_instituicao: 101 / 321 (parent institution — non-unique)
Codigo widths          : 3 or 4 (range 100..7730) → stored zero-padded to width 4
NULL geometry          : 0 / 321  ✅ (vs rede_escolar's ~10%)
Natureza distribution  : 118 Pol-Públ | 87 Univ-Públ | 64 Pol-Priv | 46 Univ-Priv | 6 Militar
```

## Quirks

- **`Código do Estabelecimento` is non-unique by design** — see the §Schema trap (2) above.
  Stored as `codigo_instituicao` and indexed but NEVER used as a join key for the higher-ed
  PK. Silver's `dim_school.higher_ed` joins to DGES rankings via `codigo_unidade_organica`.
- **4-digit codes stored as zero-padded text** (`"0100"` .. `"7730"`). Underlying DBF is
  int64; the loader pads on insert. DGES publishes acesso/colocações rankings with
  zero-padded text codes, so silver joins to [[dges-acesso]] work without re-padding.
- **`Natureza e Tipo` is stored verbatim** — 6 distinct values combining natureza
  (`Público|Privado`) × tipo (`Universitário|Politécnico|Militar e Policial …`). Silver
  may split this into two columns if needed; bronze stays raw.
- **`Distrito` includes ilhas** (e.g. `Ilha de São Miguel`, `Ilha Terceira`) where the
  CAOP source uses the parent distrito Açores. Silver normalises against CAOP.
- **No NULL geometry** in the 2026-06-07 sample (0/321) — significantly cleaner than
  [[rede-escolar]]'s ~10% gap.
- **DGEEC publishes irregularly** — the current file mtime is 2023-03-15. Manual trigger
  only; no cron. Probe quarterly by HEAD-ing the URL and comparing `Last-Modified`.

## DAGs

- `dgeec_ens_sup_ingestion` — single GET against the ATOM mirror, validates size +
  ZIP integrity + sidecar presence + pyogrio probe (CRS, geometry type, feature count
  band), uploads the ZIP intact to `s3://raw/dgeec_ens_sup/{run_date}/Estab_Ens_Sup_Portugal.zip`.
  Manual trigger.
- `dgeec_ens_sup_bronze_load` — discovers latest snapshot, downloads the ZIP, extracts
  shapefile sidecars to a temp dir, reads via `pyogrio.raw.read()` (no geopandas/shapely
  dependency — Point WKB decoded manually with `struct`), upserts into
  `bronze_education.raw_dgeec_ens_sup` with dual-CRS PostGIS geometry. Manual trigger.

Both live under `pipelines/gis/dgeec_ens_sup/`. Custom DAG shape (NOT the GIS template),
see §"Why a custom DAG".

## Last verified

2026-06-07 — ZIP downloaded (40 788 bytes) + probed live. 321 features, 321 unique
codigo_uo, 0 NULL geom. Field set matches the bronze rename map exactly (zero unknown
keys). End-to-end Airflow ingestion + bronze load both succeeded.
