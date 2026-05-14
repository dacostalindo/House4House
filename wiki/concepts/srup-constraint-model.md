---
title: SRUP constraint model — how regulatory layers gate construction on a drawn polygon
type: concept
last_verified: 2026-05-14
tags: [srup, regulatory, gis, constraint, polygon, spatial, concept]
---

## For future Claude

This is a concept page about the **SRUP constraint model**: how the 14 in-scope regulatory layers (servidões e restrições de utilidade pública) are represented, how each one constrains construction under Portuguese law, and the locked schema that sprint-09's `gold.fn_assess_polygon` queries against. Read this before writing or editing any `stg_srup_*` staging model, the `dim_constraint_severity` model, or `fn_assess_polygon`. It is the output of Sprint-08 Activity 6 PR 1 (deep research + schema design). The key finding: **most SRUP layers ARE the legally-drawn restriction zones** — the zone-type is already an attribute of each feature, so there is no geometric core-vs-buffer computation to do; the three layers that take a query-time buffer (REN linear, Rede Viária, Rede Ferroviária) carry a static per-`zone_type` `buffer_m` + `buffer_ref` in the dimension.

## What it is

The UC-3 v1 wedge primary workflow is **polygon-draw**: a user draws an arbitrary polygon on the Atlas map and the system reports every regulatory constraint that intersects it, with a severity per layer and an overall verdict. `fn_assess_polygon` (sprint-09) does this live via `ST_Intersects` against GIST-indexed staging tables — no pre-compute, because drawn polygons are unique.

This page locks the **model** behind that function:

1. **The 14 layers** in scope, their governing law, and what construction effect each imposes — researched with direct quotes from the Decretos-Lei.
2. **Geometry semantics** of each `bronze_regulatory.raw_srup_*` table (inspected live 2026-05-14).
3. **The severity model** — a relationship-aware mapping from `(constraint_code, zone_type)` to a 0–3 severity, materialized as the `dim_constraint_severity` SQL model.
4. **The constraint-hit schema** — the JSONB shape `fn_assess_polygon` returns per hit and in aggregate.

Out of scope for v1 (deferred to v1.5): wildfire risk (`raw_srup_perigosidade_inc_rural` — 1.79M polygons — and `raw_srup_sgifr_*`, which are incomplete 500-row ingests), aquifer protection (`raw_srup_aquiferos`), geodesic marks (`raw_srup_marcos_geod`), classified trees (`raw_srup_arvores_*`).

## Why

**Why a relationship-aware severity, not a per-layer scalar.** Intersecting a "zona non aedificandi" is a hard prohibition; intersecting a "zona de ocupação condicionada" of the *same* DPH regime is a softer, authorization-gated constraint. A flat per-layer severity would collapse that distinction and mislead the user.

**Why the relationship is an attribute, not a geometry computation.** The original plan (2026-05-14) assumed each layer had a *core feature* (a road centerline, a monument point) plus a *buffer* we'd derive geometrically — meaning `fn_assess_polygon` would `ST_Intersects` against both the raw geom and a `ST_Buffer`'d geom (~2× the spatial work). **Live inspection + geometry measurement of all 14 bronze tables proved this mostly right.** For most layers the geometry is already the **legally-drawn servidão polygon** — the non-aedificandi setback is pre-baked, and the zone-type is carried explicitly in the `servidao` / `tipologia` properties (or, for IC, in the geometry type). Three layers take a query-time buffer: **REN linear** (watercourse `MultiLineString`s — `buffer_m = 10`), **Rede Ferroviária** (the polygon IS the ~20 m zone, but `buffer_m = 10` covers the height-growth rule) and **Rede Viária** (the polygons are the road *corridor*, ~40 m wide, NOT the wider non-aedificandi servidão — `buffer_m = 50/35/20` by road class, measured from the axis; see that layer's entry). Even so, the buffer is a static per-`zone_type` pair of columns (`buffer_m`, `buffer_ref`) in `dim_constraint_severity`, not a per-hit geometric classification: `fn_assess_polygon` does **one** `ST_Intersects` per layer (against the raw geom, or a `ST_Buffer`'d geom where `buffer_m > 0`) and joins on `(constraint_code, zone_type)`. The plan's "relationship classification cost" risk — intersecting against both a raw and a derived geom per layer — is still avoided.

**Why a materialized dimension, not hard-coded constants.** The severity mapping is a small, slow-changing, human-auditable lookup. It is materialized as an inline-`VALUES` SQL model (`dim_constraint_severity.sql`) — the project's established pattern for static reference dimensions (`dim_property_type`, `ref_imi_rates`, `ref_imt_brackets`); the repo has no dbt-seed infrastructure. A PT-developer / domain expert can sanity-check a 27-row `VALUES` block; they can't audit a CASE statement buried in a Postgres function.

## How

### The 14 layers — legal regime + construction effect

Severity scale (locked): **3** = hard gate, construction prohibited as a rule (an exception path exists but the default answer is "no"); **2** = conditioned, construction possible only with a prior favourable opinion / authorization from the managing authority; **1** = advisory, regime largely inapplicable or minor; **0** = no constraint.

**RAN — Reserva Agrícola Nacional** · `raw_srup_ran_ogc` · DL 73/2009 art. 21–23 (am. DL 199/2015)
Art. 21 (*Ações interditas*): "São interditas todas as ações que diminuam ou destruam as potencialidades para o exercício da atividade agrícola das terras e solos da RAN, tais como: a) Operações de loteamento e obras de urbanização, construção ou ampliação...". Art. 22–23 open a closed list of non-agricultural uses, each gated by a **parecer prévio vinculativo** from the Entidade Regional da RAN. → **severity 3**, authority: Entidade Regional da RAN.

**REN areal — Reserva Ecológica Nacional (zones)** · `raw_srup_ren_areal` · DL 166/2008 art. 20–22 (am. DL 124/2019)
Art. 20/1: "Nas áreas incluídas na REN são interditos os usos e as ações... que se traduzam em: a) Operações de loteamento; b) Obras de urbanização, construção e ampliação...". Compatible uses (art. 20/2–3) must be listed in Anexo II and cleared by **comunicação prévia** to the CCDR. **Caveat:** the `tipologia` field carries `"Exclusões"` rows — land formally *excluded* from REN, which is **not a constraint** (severity 0). → **severity 3** for `reserva_ecologica`, **severity 0** for `exclusao`. Authority: CCDR.

**REN linear — REN watercourse lines/beds** · `raw_srup_ren_linear` · DL 166/2008 art. 20 (am. DL 124/2019)
Same prohibition regime as REN areal, but the geometry is a `MultiLineString` ("Linhas de Água", "Leitos dos Cursos de Água - 10 metros"). The legal *margem* for non-navigable watercourses is **10 m** from the bed edge — so this is the one layer needing a buffer (`buffer_m = 10`, applied in `fn_assess_polygon`). → **severity 3**, authority: CCDR.

**IC — Imóveis Classificados / Património Cultural** · `raw_srup_ic` · Lei 107/2001 art. 43 + 45, DL 309/2009 art. 51
Two relationships, distinguished by geometry type. Lei 107/2001 art. 43/4 (the protection zone): "não podem ser concedidas... licenças para obras de construção e para quaisquer trabalhos que alterem a topografia, os alinhamentos e as cérceas" without "prévio parecer favorável da administração do património cultural"; DL 309/2009 art. 51 makes that a **parecer prévio vinculativo** (interior-only works exempt). Art. 45/3 (the monument itself): works "serão objeto de autorização e acompanhamento do órgão competente" — stricter. In the data, `ST_Point` geom (1,122 rows) = the monument; `ST_Polygon` / `GeometryCollection` (2,551 rows) = the zona de proteção / ZEP. → `monumento` **severity 3**, `zona_protecao` **severity 2**. Authority: DGPC / Direção Regional de Cultura.

**DPH — Domínio Público Hídrico** · `raw_srup_dph` · Lei 54/2005 art. 21 + 25
The `servidao` field carries the relationship explicitly — two zone types. Art. 25/2 (*zona de ocupação edificada proibida* = the data's `"D.HÍDRICO - ZONA NON AEDIFICANDI"`): "é interdito... Realizar construções, construir edifícios ou executar obras suscetíveis de constituir obstrução à livre passagem das águas". Art. 25/5 (the data's `"D.HÍDRICO - ZONA DE OCUPAÇÃO CONDICIONADA"`): "só é permitida a construção de edifícios mediante autorização de utilização dos recursos hídricos" + flood-mitigation conditions; art. 25/7: non-compliant licenses are "nulos e de nenhum efeito". → `non_aedificandi` **severity 3**, `ocupacao_condicionada` **severity 2**. Authority: APA.

**ZPE — Zonas de Proteção Especial (Natura 2000, birds)** · `raw_srup_zpe` · DL 140/99 art. 9–10
Art. 9/2: "a realização de obras de construção civil fora dos perímetros urbanos [depende] de parecer favorável do ICN[F] ou da comissão de coordenação e desenvolvimento regional competente"; art. 10 adds the **análise de incidências ambientais** before licensing. Silence within 45 days = favourable (deferimento tácito) — a procedural gate, not an absolute veto. Small reconstruction/conservation work is exempt. → **severity 2**, authority: ICNF / CCDR.

**ZEC — Zonas Especiais de Conservação (Natura 2000, habitats)** · `raw_srup_zec` · DL 140/99 art. 9–10
Identical regime to ZPE. → **severity 2**, authority: ICNF / CCDR.

**Áreas Protegidas** · `raw_srup_areas_protegidas` · DL 142/2008 art. 23 / 23-A / 23-B
Art. 23: the *programa especial* (POAP) "estabelece... as acções permitidas, as acções condicionadas... e as acções proibidas"; art. 23-A splits each area into proteção total / parcial / complementar (total-protection zones effectively exclude construction); art. 23-B: actions may be subject to "parecer prévio vinculativo ou autorização da autoridade nacional". Reserva Natural (art. 18) is legally stricter than Paisagem Protegida (art. 19). Treated conservatively in v1 because the POAP can fully prohibit. → **severity 3**, authority: ICNF.

**Rede Viária — road non-aedificandi zones** · `raw_srup_rede_viaria` · Lei 34/2015 art. 31–32 (data cites DL 315/91)
Art. 32 defines the *zona de servidão non aedificandi* — **50 m from the road axis** for Auto-estrada/IP, 35 m for IC, 20 m for EN/ER and others. Art. 55/58: defined exceptions (ampliação/alteração of existing buildings, etc.) can be authorized by the road authority. **Geometry caveat (measured 2026-05-14):** the bronze polygons are the road *corridor* (zona da estrada) — median width Auto-estrada ~53 m, IP ~42 m, IC ~40 m, EN/ER ~40 m. The lower classes cluster at ~40 m regardless of road — the layer was digitised as fixed-width centreline buffers (~20 m half-width). So for EN/ER the corridor ≈ the 40 m zone already; for IP/IC/Auto-estrada it falls well short of the 100/70 m the from-axis servidão needs. The buffer is therefore measured **from the axis**: `zone_type` = road class (`servidao_rodoviaria_ip` / `_ic` / `_local`), `buffer_m` = 50/35/20 m, `buffer_ref = 'axis'` — `fn_assess_polygon` subtracts the per-feature half-width (~`ST_Area/ST_Perimeter`) from `buffer_m` before buffering the corridor, which exactly delivers "within X m of the axis" (a point d outside the corridor edge is half-width + d from the axis). → **severity 2**, authority: Infraestruturas de Portugal / município.

**Rede Elétrica — power-line easements** · `raw_srup_rede_eletrica` · DL 43335 + RSLEAT (DR 1/92)
DL 43335 art. 51/2: the operator's establishment license "é o título constitutivo da respetiva servidão administrativa". RSLEAT art. 30 sets the binding clearance: bare conductors must keep `D = 3,0 + 0,0075·U` metres (U in kV) from roofs/chimneys/scalable protruding parts, never less than 4 m — so new construction in the faixa is *condicionada* (allowed only if those distances are respected), not prohibited; needs the grid operator's technical clearance. The legally-drawn faixa de protecção / servidão administrativa is ~25 m (≤60 kV AT) to 45 m (RNT >60 kV MAT) wide, centred on the line axis — pre-baked into the MultiPolygon geometry. Live data (2026-05-14): the layer carries exactly two `tipologia` values — "Alta Tensão" (1618 rows) and "Muito Alta Tensão" (838 rows); every row's `serv_lei` = "Decreto-Lei n.º 43335" and `serv_hiperlig` points to `DL 43335_1960.pdf`. BT/MT lines (RSRDEEBT, DR 90/84) are NOT in this SRUP layer. Measured 2026-05-14: polygon median width 44.3 m for both classes — matches the 45 m MAT faixa and over-covers the 25 m AT strip, so `buffer_m = 0` is verified, not assumed. `zone_type` = `servidao_eletrica_at` / `servidao_eletrica_mat` (carries the E-Redes vs REN authority split). → **severity 2**, authority: E-Redes (AT) / REN (MAT).

**Rede Ferroviária — railway easements** · `raw_srup_rede_ferroviaria` + `raw_srup_rede_ferroviaria_estacoes` · DL 276/2003 art. 15
Art. 15/1/a: on properties bordering railway lines it is prohibited to "fazer construções, edificações, aterros... a distância inferior a 10 m". **The 10 m runs from the *linha férrea* (the track), not the domain boundary** (verified against DL 276/2003 art. 15/1/a; the law leaves rail-edge-vs-centreline to delimitation) — so the zone is ~10 m each side ≈ 20 m total. Art. 15/2: the distance grows with structure height > 10 m. Art. 15/5: high-speed lines (≥ 220 km/h) get ≥ 25 m — not yet relevant in PT. Measured 2026-05-14: polygon median width 19.8 m matches the ~20 m zone — so `buffer_m = 10` is applied on top (`buffer_ref = 'geom'`) to cover the art. 15/2 height-growth rule, not to fix a geometry gap. **Relationship from `tipologia`:** active lines ("Com exploração", "Troço Fronteiriço") carry the full prohibition; disused lines ("Sem exploração", "Antigo Traçado") have a largely extinguished regime. The companion `raw_srup_rede_ferroviaria_estacoes` layer (station + halt yards — same DL 276/2003 regime, wider footprints than the 20 m line corridor) is folded in as a third `zone_type`. → `servidao_ferroviaria_ativa` **severity 3** (`buffer_m = 10`), `servidao_ferroviaria_estacao` **severity 3** (`buffer_m = 10`), `servidao_ferroviaria_inativa` **severity 1** (`buffer_m = 0`). Authority: Infraestruturas de Portugal.

**Albufeiras — public-reservoir protection zones** · `raw_srup_albufeiras` · DL 107/2009 art. 12–21
Art. 12 defines the *zona terrestre de protecção* (default 500 m from the full-storage line), Art. 13 a 100 m *zona reservada* within it; Art. 21 lists loteamento / construção / ampliação as *interditas* in the zona reservada, Art. 19–20 make urban operations in the wider ZTP *condicionadas* subject to a **parecer prévio vinculativo da ARH** (Art. 35/2: ARH opinions are always binding). The `tipologia` field carries a clean 3-tier split: `"ALBUFEIRAS PROTEGIDAS"` (public-supply / high conservation value — near-total construction ban), `"ALBUFEIRAS CONDICIONADAS"` (build only with binding prior opinion), `"ALBUFEIRAS DE UTILIZAÇÃO LIVRE"` (general rules apply, but the ZTP/zona reservada limits still bite). → `protegida` **severity 3**, `condicionada` **severity 2**, `livre` **severity 2** (the SRUP polygon IS the protection zone, so intersecting it is still conditioned). Authority: APA / ARH.

**Defesa Militar — military servitudes** · `raw_srup_defesa_militar` + `raw_srup_defesa_militar_zonas` · Lei 2078/1955 + DL 45986/1964
In a zone subject to a military servitude, "construções de qualquer natureza", changes to building heights, terrain alteration and tree planting are **prohibited without authorization of the Ministério da Defesa Nacional**. Each servitude's own constituting decree subdivides the area into graduated zones (Zona 1 innermost/strictest → Zona 4 outermost). Two bronze tables are UNION'd into one staging model; `zone_type` collapses the graduation into two tiers: `nucleo` (TERRENO MILITAR / "MILITAR - SERVIDÃO" / Zona 1 — effective construction ban) and `zona_protecao` (Zona 2/3/4, edifícios públicos & património cultural protection — authorization required, lighter at the outer band). → `nucleo` **severity 3**, `zona_protecao` **severity 2**. Authority: Ministério da Defesa Nacional. *(Confidence: medium — Lei 2078 / DL 45986 are pre-1974 scanned texts; the prohibition/authorization structure is reliable, exact metric widths live in each feature's individual constituting decree.)*

**Aeronáutica — aeronautical servitudes** · `raw_srup_aeronautica` · DL 45987/1964
Servitude zones around aerodromes, air bases and radio beacons, to guarantee air-navigation safety. The `tipologia` field splits three ways: `"AERONÁUTICA - ÁREA DE DESOBSTRUÇÃO"` (the obstacle-clearance surfaces — anything penetrating the height limits is **prohibited**; sub-limit construction still needs binding ANAC / Força Aérea parecer — treated as a hard gate since the area is height-critical), `"AERONÁUTICA - SERVIDÃO"` (general height-capped servitude — conditioned on authorization), `"AERONÁUTICA - ZONA PROTEÇÃO EDIFÍCIOS PÚBLICOS"` (conditioned, lighter). → `area_desobstrucao` **severity 3**, `servidao` **severity 2**, `zona_protecao` **severity 2**. Authority: ANAC / Força Aérea. *(Confidence: medium — DL 45987 is a pre-1974 scanned text; structure reliable, metric thresholds per-installation.)*

### Geometry semantics (inspected live 2026-05-14)

| Layer | Geometry type(s) | Count | zone_type derivation |
|---|---|---|---|
| `raw_srup_ran_ogc` | MultiPolygon | 268 | constant `reserva_agricola` |
| `raw_srup_ren_areal` | MultiPolygon | 405 | `tipologia ILIKE '%exclus%'` → `exclusao`, else `reserva_ecologica` |
| `raw_srup_ren_linear` | MultiLineString | 144 | constant `linha_de_agua` (buffer 10 m at query time) |
| `raw_srup_ic` | Point 1122 / Polygon 2222 / GeometryCollection 329 | 3673 | `ST_GeometryType = 'ST_Point'` → `monumento`, else `zona_protecao` |
| `raw_srup_dph` | Polygon 4 / GeometryCollection 3 | 7 | `servidao ILIKE '%NON AEDIFICANDI%'` → `non_aedificandi`, else `ocupacao_condicionada` |
| `raw_srup_zpe` | MultiPolygon | 44 | constant `rede_natura` |
| `raw_srup_zec` | MultiPolygon | 65 | constant `rede_natura` |
| `raw_srup_areas_protegidas` | MultiPolygon | 69 | constant `area_protegida` |
| `raw_srup_rede_viaria` | MultiPolygon | 3160 | `tipologia` `(IP)`/`Auto-estrada` → `servidao_rodoviaria_ip`, `(IC)` → `_ic`, else `_local` |
| `raw_srup_rede_eletrica` | MultiPolygon | 2456 | `tipologia ILIKE '%Muito Alta%'` → `servidao_eletrica_mat`, else `servidao_eletrica_at` |
| `raw_srup_rede_ferroviaria` | MultiPolygon | 502 | `tipologia ILIKE '%sem explora%' OR '%antigo%'` → `servidao_ferroviaria_inativa`, else `servidao_ferroviaria_ativa` |
| `raw_srup_rede_ferroviaria_estacoes` | MultiPolygon | 860 | constant `servidao_ferroviaria_estacao` (UNION'd into `stg_srup_rede_ferroviaria`) |
| `raw_srup_albufeiras` | MultiPolygon | 191 | `tipologia` PROTEGIDAS → `protegida`, CONDICIONADAS → `condicionada`, LIVRE → `livre` |
| `raw_srup_defesa_militar` + `_zonas` | MultiPolygon | 147 + 149 | UNION'd; TERRENO MILITAR / SERVIDÃO / Zona 1 → `nucleo`, else `zona_protecao` |
| `raw_srup_aeronautica` | MultiPolygon | 35 | `tipologia` DESOBSTRUÇÃO → `area_desobstrucao`, SERVIDÃO → `servidao`, else `zona_protecao` |

Key consequence: 5 of the 14 layers have a single `zone_type` (RAN, REN linear, ZPE, ZEC, Áreas Protegidas — the whole layer IS one restriction zone); the other 9 split into two or three. The `zone_type` column is added by each `stg_srup_*` staging model (PR 2) using the derivation above — it is **not** computed in `fn_assess_polygon`. Three layers carry a non-zero `buffer_m` applied at query time: REN linear (10 m, `buffer_ref = 'geom'`), Rede Ferroviária (10 m, `'geom'` — height-rule margin) and Rede Viária (50/35/20 m by class, `buffer_ref = 'axis'` — half-width-corrected).

### The severity model — `dim_constraint_severity`

Materialized as an inline-`VALUES` SQL model (`dbt/models/gold/dim_constraint_severity.sql`), keyed on `(constraint_code, zone_type)`. Columns:

- `constraint_code` — RAN, REN_areal, REN_linear, IC, DPH, ZPE, ZEC, AreasProtegidas, RedeViaria, RedeEletrica, RedeFerroviaria, Albufeiras, DefesaMilitar, Aeronautica
- `zone_type` — the relationship attribute (see derivation table above)
- `severity` — 0–3 (scale above)
- `category` — agricultural | ecological | heritage | water_domain | conservation | infrastructure | military | aviation
- `buffer_m` — metres to `ST_Buffer` before intersection: 0 where the polygon already IS the servidão; 10 for REN_linear and active/station Rede Ferroviária; 50/35/20 for Rede Viária by class
- `buffer_ref` — `'geom'` (buffer the stored geometry directly) or `'axis'` (buffer_m is from the road axis — `fn_assess_polygon` subtracts the per-feature half-width first; Rede Viária only)
- `legal_basis` — governing Decreto-Lei + article range
- `requires_prior_opinion` — whether a legal exception path via an authority opinion exists
- `authority` — the entity that issues that opinion / authorization

Derived in `dim_constraint_severity.sql`: `is_hard_gate` (`severity >= 3`), `is_conditioned` (`severity = 2`), `is_advisory` (`severity = 1`), `severity_label`, `display_color` (3 → `#d32f2f`, 2 → `#f57c00`, 1 → `#fbc02d`, 0 → `#9e9e9e`).

The model has **27 rows**: RAN 1, REN_areal 2, REN_linear 1, IC 2, DPH 2, ZPE 1, ZEC 1, AreasProtegidas 1, RedeViaria 3, RedeEletrica 2, RedeFerroviaria 3, Albufeiras 3, DefesaMilitar 2, Aeronautica 3.

### The constraint-hit schema (locked — `fn_assess_polygon` returns this in sprint-09)

Per intersecting layer, one hit object:

```json
{
  "constraint_code": "DPH",
  "layer": "stg_srup_dph",
  "zone_type": "non_aedificandi",
  "severity": 3,
  "severity_label": "Hard gate",
  "category": "water_domain",
  "label": "D.HÍDRICO - ZONA NON AEDIFICANDI",
  "designation": "<feature designacao>",
  "overlap_pct": 0.42,
  "legal_basis": "Lei 54/2005 art. 25",
  "authority": "APA",
  "requires_prior_opinion": true
}
```

(`layer` is the staging-model name the hit came from; `designation` is the feature's `designacao`. `buffer_m` / `buffer_ref` are not surfaced in the hit — they are inputs to the intersection, not output facts.)

`overlap_pct = ST_Area(ST_Intersection(input_3763, layer_geom_3763)) / ST_Area(input_3763)` — the fraction of the drawn polygon inside this layer; gives the "30% of your plot is in RAN" nuance, cheap to compute.

Aggregate return:

```json
{
  "verdict": "blocked",
  "max_severity": 3,
  "blocked_by": ["RAN", "DPH"],
  "conditioned_by": ["IC", "ZPE"],
  "layers_checked": 14,
  "hits": [ ... ]
}
```

`verdict` = `blocked` if `max_severity >= 3`, `conditioned` if `= 2`, `clear` if `<= 1`. The frontend shows the verdict AND the full `hits` list — per the user-locked decision, the Inspector surfaces every layer, not just the max.

### What sprint-09 builds on this

`gold.fn_assess_polygon(input_geom geometry) RETURNS jsonb` — `ST_Transform` the input to 3763, one `ST_Intersects` per `stg_srup_*` layer (REN_linear + Rede Ferroviária buffered by `buffer_m`; Rede Viária buffered by `buffer_m` minus per-feature half-width per `buffer_ref = 'axis'`), join `dim_constraint_severity` on `(constraint_code, zone_type)`, assemble the hit list + aggregate. Plus the non-SRUP layers (zoning, land_use, terrain/slope, assembled parcels) and the Atlas Site Inspector UI.

## See also

- [[srup]] — the legacy WFS SRUP source page (IC + DPH still ingested this way)
- [[srup-ogc]] — the OGC API SRUP source page (RAN migrated here; the rest of the 14 layers)
- [[spatial-strategy]] — dual-CRS storage + GIST indexing that makes `ST_Intersects` fast
- [[medallion-layering]] — where `stg_srup_*` (staging) and `dim_constraint_severity` (gold) sit
- [[sprint-08]] — Activity 6 PR 1 (this page + the severity dimension), PR 2 (the staging models + GIST plumbing), PR 3 (SRUP `properties` JSONB schema breakdown)
- [[sprint-09]] — `fn_assess_polygon` body + the Atlas Site Inspector UI
