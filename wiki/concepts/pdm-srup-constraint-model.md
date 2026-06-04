---
title: PDM + SRUP constraint model
type: concept
last_verified: 2026-06-04
tags: [regulatory, pdm, srup, fn-assess-polygon, architecture]
---

## For future Claude

This concept page documents the **dual-layer regulatory constraint model** that `fn_assess_polygon` consumes: PDM (local Plano Diretor Municipal rules) + SRUP (national Servidões e Restrições de Utilidade Pública overlays). The model is **complementary, not redundant** — PDM tells you what the local plan says; SRUP tells you what national legal regime applies spatially. Read this before touching `dim_pdm_constraint`, `dim_constraint_severity`, `silver_regulatory.srup_constraints`, or [silver_geo.zoning](../../dbt/models/silver/geo/zoning.sql).

## What it is

Three dims/silvers cooperate to answer "what can I build on this drawn polygon?":

| Object | Layer | Grain | What it carries |
|---|---|---|---|
| `gold_analytics.dim_constraint_severity` | gold dim | one row per (SRUP `constraint_code`, `zone_type`) | severity 0-3 + authority + legal_basis + buffer_m + display_color — from **national law** (DL/Lei references) |
| `gold_analytics.dim_pdm_constraint` | gold dim | one row per atomic Regulamento clause | verbatim source_text + constraint_type + **zone_pattern TEXT[]** (array of values the row matches: subcategoria, umbrella slug, AND/OR SRUP layer codes) + applies_to_zone_types + applies_when_land_classification — from the **local PDM** |
| `silver_regulatory.srup_constraints` | silver | one row per spatial SRUP feature (UNION ALL of 15 stg_srup_*) | spatial geom + denormalized severity attrs + **municipality_codes TEXT[]** (multi-município support) + pdm_constraint_keys[] (from dim_pdm_constraint, aggregated per feature) |
| `silver_geo.zoning` | silver | one row per CRUS polygon | the local plan zoning (Solo Urbano/Rústico × subcategoria) + applicable_pdm_constraint_keys[] (matched by subcategoria + umbrella slugs only) |

## Why

### The regulatory stack has two layers

The Portuguese planning law has a clear hierarchy:

- **National law** (DL 73/2009 RAN, DL 166/2008 REN, Lei 107/2001 Património, DL 140/99 Rede Natura, DL 124/2006 PMDFCI, DL 115/2010 ARPSI, etc.) sets the **baseline regime** — these are the SRUP layers. They apply spatially across all 308 municípios.
- **Local PDM Regulamento** (Aveiro 2019, Coimbra 2022, etc.) sets município-specific rules on top of the national regime — adds local-plan zoning, plus elaborations + exceptions where it cites the national overlays.

The PDM **mostly defers to national law** for SRUP-layer severities (e.g. Art. 53 Aveiro: "integrados na Reserva Agrícola Nacional (RAN)" — no severity stated locally; the RAN regime says non-edificandi). For 11 of 15 SRUP layers the PDM at least mentions the layer by name; for the other 4 (DPH, Albufeiras, RedeEletrica, Aeronautica) the PDM only lists them in Art. 6 inventory.

So the severities live in:
- `dim_constraint_severity` — canonical national severity per (constraint_code, zone_type). Stable, doesn't change per município.
- `dim_pdm_constraint` — implicit severity via `constraint_type` enum (prohibition=3, required_approval=2, conditional_permission=2, spatial_setback=2, numeric_limit=parameter, dominant_use/compatible_use=1). Município-specific elaborations.

Both are kept and both get consulted; **`fn_assess_polygon` picks the more restrictive of the two** when both fire.

### Why the dims attach at the SRUP feature level, not the zoning polygon level

Initial attempt: pre-compute applicable SRUP overlay constraints per `silver_geo.zoning` polygon by spatial intersect.

Problem: **zoning polygons are too coarse**. Aveiro has 1148 polygons but the SRUP features overlap them at much finer granularity (3k+ Aveiro features across 15 layers). A 200-ha "Outros Espaços Agrícolas" zoning polygon may have RAN covering 53% of its area but a portion outside RAN — pre-joining at the zoning grain loses that spatial precision.

Resolution: **the dim joins happen at the SRUP feature level** in `silver_regulatory.srup_constraints`. Each SRUP feature (typically ~1-5 ha for Aveiro features) carries:
- Its own geometry (precise spatial extent)
- Severity attrs from `dim_constraint_severity` (joined by `constraint_code + zone_type`)
- Aggregated PDM rule keys from `dim_pdm_constraint` (joined by `municipality_code + zone_pattern = constraint_code`)

`fn_assess_polygon` then queries TWO spatial silvers when assessing a drawn polygon:
1. `silver_geo.zoning` — PDM-by-zone constraints (matched via subcategoria + ALL_* umbrellas)
2. `silver_regulatory.srup_constraints` — PDM-by-spatial-overlay + national severity

The union of both answers gives the full constraint set.

## How

### zone_pattern is TEXT[] — every value the row matches in one array

`dim_pdm_constraint.zone_pattern` is a **TEXT[] array** carrying every value the row can be matched by. For most rows this is a single value (e.g. just `{Espaço Habitacional Tipo 1}`). For rows whose PDM article invokes one or more SRUP overlays, the array also includes the SRUP layer code(s):

| Row example | zone_pattern array |
|---|---|
| Art. 99 Esp. Habitacional Tipo 1 | `{Espaço Habitacional Tipo 1}` |
| Art. 53 Esp. Agrícola de Produção (invokes RAN) | `{Espaço Agrícola de Produção, RAN}` |
| Art. 57 Esp. Florestal de Proteção (invokes REN+ZPE+PORNDSJ) | `{Espaço Florestal de Proteção, REN_areal, REN_linear, ZPE, AreasProtegidas}` |
| Art. 33 Espaços Canais (invokes Rede Viária + Ferroviária) | `{ESPACOS_CANAIS, RedeViaria, RedeFerroviaria}` |
| Art. 51/1/a Perigosidade hard-gate | `{Perigosidade_Incendio_Rural}` |
| Art. 41/1 Critérios gerais | `{ALL_PDM}` |
| Art. 49/a Solo Rústico admissões | `{ALL_SOLO_RUSTICO}` |

Each element in the array falls into one of four categories:

| Element type | Examples | Matched by silver consumer |
|---|---|---|
| **Subcategoria** | `Espaço Habitacional Tipo 1`, `Curso de água` | `silver_geo.zoning.subcategoria` (exact equality) |
| **Umbrella** | `ALL_PDM`, `ALL_SOLO_URBANO`, `ALL_SOLO_RUSTICO` | `silver_geo.zoning.land_classification` (or universally for ALL_PDM) |
| **SRUP layer code** | `RAN`, `ZPE`, `ZEC`, `Perigosidade_Incendio_Rural`, etc. | `silver_regulatory.srup_constraints.constraint_code` (via spatial intersect) |
| **Local-overlay** (not yet ingested as SRUP) | `EEM`, `POC_OMG*`, `EQUIPAMENTOS_EDUCATIVOS`, `UOPG*`, etc. | Each needs its own silver overlay layer (deferred) |

Population path: the markdown source file [[aveiro-pdm]] has a per-row primary `zone_pattern` cell PLUS a dedicated "Zone-pattern ↔ SRUP cross-reference" section that lists which SRUP layers each primary pattern invokes. The Python generator merges these into the final TEXT[] array at dim build time.

The two filter columns refine the match further:
- `applies_to_zone_types TEXT[]` — for SRUP-overlay matches where the rule applies only to specific zone_types. Example: PDM Art. 51/1/a fires only on `{perigosidade_alta, perigosidade_muito_alta}` features (hard gate), not on média/baixa/muito_baixa.
- `applies_when_land_classification TEXT` — for cross-cutting rules with a land_classification predicate. Example: PDM Art. 10/2 fires only when polygon ∩ ZPE AND `land_classification = 'Solo Rústico'`.

### Materialization pattern

`silver_regulatory.srup_constraints` materializes:

```sql
WITH srup_union AS (
    -- UNION ALL of 15 stg_srup_* with 'source_layer' tag prefix
)
SELECT
    [columns from srup_union],
    muni.municipality_codes,                       -- TEXT[] — supports multi-município features
    [denormalized severity attrs from dim_constraint_severity via sev LEFT JOIN],
    pdm.pdm_constraint_keys,
    pdm.pdm_rule_count,
    pdm.pdm_articles,
    pdm.pdm_constraint_types
FROM srup_union u
LEFT JOIN LATERAL (
    -- Multi-município resolution: split comma-separated municipality_text on ','
    -- then JOIN dim_geography. Empty array for national-scope features.
    SELECT
        COALESCE(ARRAY_AGG(g.concelho_code) FILTER (WHERE g.concelho_code IS NOT NULL), '{}'::TEXT[]) AS municipality_codes,
        ...
    FROM unnest(string_to_array(COALESCE(u.municipality, ''), ',')) AS m_raw
    LEFT JOIN dim_geography g ON UPPER(TRIM(g.concelho_name)) = UPPER(TRIM(m_raw))
) muni ON TRUE
LEFT JOIN dim_constraint_severity sev
    ON sev.constraint_code = u.constraint_code AND sev.zone_type = u.zone_type
LEFT JOIN LATERAL (
    SELECT
        ARRAY_AGG(d.pdm_constraint_key ORDER BY d.pdm_constraint_key) AS pdm_constraint_keys,
        COUNT(*)::INTEGER                                              AS pdm_rule_count,
        ARRAY_AGG(DISTINCT d.legal_article  ORDER BY d.legal_article)  AS pdm_articles,
        ARRAY_AGG(DISTINCT d.constraint_type ORDER BY d.constraint_type) AS pdm_constraint_types
    FROM dim_pdm_constraint d
    WHERE d.municipality_code = ANY(muni.municipality_codes)
      AND u.constraint_code   = ANY(d.zone_pattern)
      AND (d.applies_to_zone_types IS NULL OR u.zone_type = ANY(d.applies_to_zone_types))
) pdm ON TRUE
```

`applies_when_land_classification` is **not applied here** — at SRUP feature build time we don't know the future polygon's classification. The filter is applied at query time in fn_assess_polygon when combining a SRUP feature hit with a zoning polygon hit.

### Coverage status (2026-06-04, Aveiro v1)

- `dim_pdm_constraint`: 314 rows for município 0105 (Aveiro), 100% subcategoria coverage of 1148 zoning polygons
- `dim_constraint_severity`: 36 rows national + Aveiro-specific Perigosidade additions
- `silver_regulatory.srup_constraints`: ~1.8M features nationally (Aveiro ~3k)
- `silver_geo.zoning`: 236,920 polygons nationally (Aveiro 1148 covered 100%)

## Audit findings (2026-06-04 — strict-regex audit of source_text)

True coverage of SRUP layers in `dim_pdm_constraint` (rows whose source_text literally cites the layer):

| SRUP layer | PDM rows | Status |
|---|---|---|
| RAN | 3 (Art. 52/1/a, 53, 55) | PDM defers to RAN regime; severity from national law |
| REN_areal + REN_linear | 3 (Art. 57, 61) | PDM doesn't distinguish areal vs linear |
| IC | 1 (Art. 11) | Required-approval regime via tutela |
| ZPE / ZEC | 5 shared (Art. 10/1/a, 10/2, 57, 61×2) | Rede Natura prohibition + parecer ICNB |
| AreasProtegidas | 17 (via PORNDSJ zone_pattern rows) | Full Capítulo III section |
| DefesaMilitar | 1 (Art. 64-65) | PM12+PM41 S. Jacinto |
| RedeViaria + RedeFerroviaria | 3 shared (Art. 33/1, 33/2, 114) | Espaços Canais |
| ARPSI_Floodplain | 3 (Art. 8) | Zonas Inundáveis + Eclusas |
| Perigosidade_Incendio_Rural | 5 (Art. 51) | Wildfire risk hard-gate + conditional |
| **DPH / Albufeiras / RedeEletrica / Aeronautica** | **0** | **National-only — no PDM article** |

`dim_constraint_severity` carries the load for the 4 national-only layers.

## Open questions / future work

- **Other overlay layers not in srup_constraints yet**: EEM (Estrutura Ecológica Municipal — Aveiro-local), POC_OMG (Programa da Orla Costeira — sector plan), PATRIMONIO_ARQUEOLOGICO (Anexo B local), EQUIPAMENTOS_EDUCATIVOS (Art. 25), UOPG1/2 (Art. 126-127). Each needs its own silver overlay table if we want to resolve them spatially.
- **Multi-município rollout**: schema accommodates `municipality_code` but the markdown source `wiki/sources/aveiro-pdm.md` is Aveiro-only. Coimbra (0603), Lisboa (1106), Porto (1312), Leiria (1010) extracted separately.
- **Severity reconciliation**: when both `dim_constraint_severity` and `dim_pdm_constraint` carry severity for the same (polygon, layer), fn_assess_polygon picks max. Document the policy explicitly when fn_assess_polygon ships.

## See also

- [[crus-ogc]] — CRUS national OGC source feeding `silver_geo.zoning` (the PDM zoning layer)
- [[srup]] — the 14 legacy SRUP staging layers (+ new Perigosidade) consolidated in `silver_regulatory.srup_constraints`
- [[UC-3]] — the use case (`fn_assess_polygon`) consuming both dims
- [[aveiro-pdm]] — the source markdown that generates `dim_pdm_constraint`
- [[sprint-09]] — the sprint where WS5 work landed

## Last verified

2026-06-04 — initial concept page written during context-save before /compact. Branch `feature/dim-pdm-constraint-aveiro`, uncommitted.
