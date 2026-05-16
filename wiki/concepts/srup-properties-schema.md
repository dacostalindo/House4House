---
title: SRUP properties JSONB schema — per-key breakdown of the 14 constraint layers
type: concept
last_verified: 2026-05-14
tags: [srup, regulatory, gis, schema, jsonb, staging, concept]
---

## For future Claude

This is a concept page documenting the **`properties` JSONB schema** of the 16 `bronze_regulatory.raw_srup_*` tables behind the 14 SRUP constraint layers — every key, its type, fill-rate, and meaning. The `stg_srup_*` staging models (Sprint-08 Activity 6 PR 2) unpack these JSONB blobs into typed columns; this page is the reference for what each key means. Read it before editing a `stg_srup_*` model or adding a new SRUP layer. Companion to [[srup-constraint-model]] (the severity/zone_type model) and the source pages [[srup]] / [[srup-ogc]]. Inventory captured live 2026-05-14.

## What it is

The SRUP bronze tables store each feature's attributes as a `properties` JSONB blob (the [[bronze-permissive]] convention — bronze keeps the source shape). The `stg_srup_*` staging models extract every key into a typed, named column. This page is the per-key dictionary.

**Two key-case conventions:**

- **OGC layers** (12 tables — `ran_ogc`, `ren_areal`, `ren_linear`, `zpe`, `zec`, `areas_protegidas`, `rede_viaria`, `rede_eletrica`, `rede_ferroviaria`, `rede_ferroviaria_estacoes`, `albufeiras`, `defesa_militar`, `defesa_militar_zonas`, `aeronautica`) use **lowercase snake_case** keys.
- **Legacy WFS layers** (2 tables — `ic`, `dph`) use **UPPERCASE** keys.

`stg_srup_*` models normalise both to lowercase English column names.

## Why

Without a unpacked schema, every consumer (`fn_assess_polygon`, the Atlas Inspector, ad-hoc queries) has to know the JSONB key names and case convention by heart, and the OGC-vs-WFS split is a silent trap. Unpacking into typed columns + this reference page makes the SRUP layers queryable like any other table. The raw `properties` JSONB is still carried on each staging model as a passthrough safety-net.

## How

### Common OGC keys (shared across most of the 12 OGC layers)

| Key | Type | Meaning | → staging column |
|---|---|---|---|
| `fid` | int (text) | OGC feature id — **duplicates the bronze `feature_id` column**, not re-extracted | (use `feature_id`) |
| `designacao` | text | Feature name / designation | `designation` |
| `servidao` | text | The servidão (restriction) label | `restriction_type` |
| `tipologia` | text | Typology / sub-classification — drives `zone_type` for most layers | `typology` |
| `lei_tipo` | text | Legal-instrument type/reference (e.g. `DL 73/2009`) | `law_type` |
| `serv_lei` | text | Specific law / regulation (e.g. `RCM 89/96`) | `restriction_law` |
| `serv_dr` | text | Diário da República reference | `dr_reference` |
| `serv_data` | text (date-like) | Date the servidão was established/published — kept as text (mixed formats) | `restriction_date` |
| `serv_hiperligacao` / `serv_hiper` / `serv_hiperlig` | text | Hyperlink to the source document (key name varies by layer — `COALESCE`d) | `restriction_url` |
| `municipios` / `concelho` / `conselho` / `municipio` | text | Municipality name(s) (key name varies — `COALESCE`d; `conselho` is a source typo in `rede_ferroviaria`) | `municipality` |

Layers whose **only** keys are the common set (no extras): `ran_ogc`, `zpe`, `zec`, `albufeiras`, `defesa_militar`, `defesa_militar_zonas`, `aeronautica`.

### Layer-specific extra keys

**`raw_srup_areas_protegidas`** (11 keys = common + 1)
| Key | Type | Meaning | → staging column |
|---|---|---|---|
| `codigo` | text | Protected-area code (fill ~90%) | `codigo` |

**`raw_srup_rede_viaria`** (11 keys = common + 1)
| `codigo` | text | Road segment code | `codigo` |

**`raw_srup_rede_ferroviaria`** (11 keys = common + 1)
| `codigo` | text | Railway segment code | `codigo` |

**`raw_srup_rede_ferroviaria_estacoes`** (11 keys = common + 1)
| `codigo` | text | Station code | `codigo` |

**`raw_srup_rede_eletrica`** (11 keys = common + 1)
| `dtcc` | text | DTCC code (distrito+concelho) | `dtcc` |

**`raw_srup_ren_areal`** (24 keys = common + 14)
| Key | Type | Meaning | → staging column |
|---|---|---|---|
| `area_ha` | double | Zone area in hectares | `area_ha` |
| `classifica` | text | Classification — **empty in all rows** | `classifica` |
| `codigoobje` | text | Object code | `codigoobje` |
| `dinamica` | text | Plan dynamic (e.g. `Revisão`) | `dinamica` |
| `dtcc` | text | DTCC code | `dtcc` |
| `fid_1` | text | Alternate feature id (float-formatted, e.g. `99.0`) | `fid_1` |
| `geom_autor` | text | Geometry author/source | `geom_autor` |
| `geom_data` | text (date-like) | Geometry date | `geom_data` |
| `geom_rigor` | text | Geometry rigor / map scale (e.g. `1/5000`) | `geom_rigor` |
| `id` | text | Internal record id (float-formatted) | `id` |
| `peca_grafi` | text | Graphic piece — the planning map (e.g. `Planta de Condicionantes-REN`) | `peca_grafi` |
| `regiao` | text | Region (e.g. `NORTE`) | `regiao` |
| `reg_n` | text | Registration number (non-numeric, e.g. `05.08.16.00/OA-92.PD`) | `reg_n` |
| `tutela` | text | Supervising authority (e.g. `DRAOT NORTE`) | `tutela` |

**`raw_srup_ren_linear`** (20 keys = common + 12; **no `serv_dr` / `serv_hiper`** keys → `dr_reference` / `restriction_url` resolve to NULL)
| Key | Type | Meaning | → staging column |
|---|---|---|---|
| `compriment` | double | Watercourse length in metres | `compriment` |
| `classifica` | text | Classification — **empty in all rows** | `classifica` |
| `codigoobje` | text | Object code | `codigoobje` |
| `dinamica` | text | Plan dynamic | `dinamica` |
| `dtcc` | text | DTCC code | `dtcc` |
| `estado` | text | Status (e.g. `Em Vigor`) | `estado` |
| `geometria_` | text (date-like) | Geometry date (truncated key name) | `geometria_` |
| `id`, `id1`, `id_servdao`, `id_servida` | text | Internal record ids | same |
| `regiao` | text | Region | `regiao` |

### Legacy WFS layers — UPPERCASE keys

**`raw_srup_ic`** (21 keys) — Imóveis Classificados / Património Cultural
| Key | Type | Meaning | → staging column |
|---|---|---|---|
| `DESIGNACAO` | text | Heritage site name | `designation` |
| `SERVIDAO` | text | Servidão label | `restriction_type` |
| `CLASSIFICACAO` | text | Heritage class (MN / IIP / ZEP / SIM / VC ...) — drives nothing here; `zone_type` is from geometry type | `typology` |
| `LEI_TIPO` | text | Legal-instrument type (fill ~96%) | `law_type` |
| `SERV_LEI` | text | Specific law (fill ~94%) | `restriction_law` |
| `SERV_DR` | text | DR reference (fill ~99.7%) | `dr_reference` |
| `SERV_DATA` | text (date-like) | Servidão date (fill ~99.8%) | `restriction_date` |
| `SERV_HIPERLINK` | text | Document hyperlink (fill ~93%) | `restriction_url` |
| `MUNICIPIOS` | text | Municipality name(s) | `municipality` |
| `AREA_HA` | double | Area in hectares (fill ~99%) | `area_ha` |
| `ESTADO` | text | Status (e.g. `Em Vigor`) | `estado` |
| `FREGUESIAS` | text | Parish name(s) (fill ~75%) | `freguesias` |
| `GEOMETRIA_AUTOR` | text | Geometry author | `geometria_autor` |
| `GEOMETRIA_DATA` | text (date-like) | Geometry date (fill ~52%) | `geometria_data` |
| `GEOMETRIA_RIGOR` | text | Geometry rigor (e.g. `WFS`) | `geometria_rigor` |
| `ID` | text | Internal record id | `id` |
| `LOCAL` | text | Location description (fill ~90%) | `local` |
| `NOTAS_GEOREF` | text | Georeferencing notes (e.g. `Sim`) | `notas_georef` |
| `REGIAO` | text | Region | `regiao` |
| `SITUACAO` | text | Situation (e.g. `Revisão`) | `situacao` |
| `TUTELA` | text | Supervising authority | `tutela` |

**`raw_srup_dph`** (18 keys) — Domínio Público Hídrico. Same key set as `ic` **minus** `CLASSIFICACAO`, `FREGUESIAS`, `NOTAS_GEOREF` (so `typology` is NULL in `stg_srup_dph`). `LOCAL` is present but empty in all rows. `zone_type` is derived from `SERVIDAO`.

### Type-casting policy

Staging models extract every key as `TRIM(...)` **text**, except two reliably-numeric keys cast to `DOUBLE PRECISION` via `NULLIF(TRIM(...), '')::DOUBLE PRECISION`: `area_ha` (`ic`, `dph`, `ren_areal`) and `compriment` (`ren_linear`). Date-like keys (`serv_data`, `geom_data`, `geometria_`, `GEOMETRIA_DATA`) stay text — the source uses mixed formats (`2026/03/04 00:00:00.000`, `2025-12-30T00:00:00`, `2023-10-12T00:00:00+00:00`) that don't cleanly cast. Id/code keys (`id`, `dtcc`, `reg_n`, `codigoobje`, `fid_1`, ...) stay text — they carry leading zeros, float-formatting, or non-numeric values.

## See also

- [[srup-constraint-model]] — the `(constraint_code, zone_type)` → severity model that consumes these staging columns
- [[srup]] — legacy WFS SRUP source page (ic + dph)
- [[srup-ogc]] — OGC API SRUP source page (the other 12 tables)
- [[bronze-permissive]] — why bronze keeps the raw `properties` JSONB and staging does the unpacking
- [[sprint-08]] — Activity 6 PR 2 (the staging models + this page)
