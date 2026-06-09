{{
  config(
    materialized='table'
  )
}}

-- Bridge table: Público school id (eid) ↔ DGEEC 6-digit school code
-- (codigo_escola). Resolves Open Q #2 from
-- [[pt-education-amenity-pillar]]. One row per publico_eid; unmatched
-- Público schools surface explicitly with codigo_dgeec=NULL and
-- match_method='unmatched' so downstream consumers know they exist but
-- can't be enriched.
--
-- Two match paths (per the empirical-probe-driven algorithm locked
-- 2026-06-09):
--
-- Path 1 — `direct_uo_fuzzy` (9ano only, codigo_uo_dgeec populated):
--   Restrict rede_escolar candidates to the school's agrupamento
--   (codigo_uo = publico.codigo_uo_dgeec), then pick the best
--   name-similarity match. Empirically 921/921 (100%) of 9ano-with-coduo
--   resolve at avg sim=0.992; no threshold needed because the UO scope
--   already provides strong evidence the schools belong together.
--
-- Path 2 — `fuzzy_spatial` (all sec + 9ano-without-coduo):
--   Candidates within 500m ST_DWithin, pick max name similarity,
--   require sim >= 0.6 (L3 lock — eyeballed 0.6 quality is bulletproof;
--   0.4-0.6 band has ~30% false positives like "Colégio Liverpool" vs
--   "Grande Colégio Universal"). NO concelho-name gate — costs island
--   coverage where Público labels concelhos like "Lagoa (R.A.A)" vs
--   DGEEC's just "Lagoa".
--
-- The id_publico ↔ DGEEC prefix probe (LEFT(codigo_escola, 4) =
-- LPAD(id_publico, 4)) was tested and matches 0/661 sec schools —
-- Público's `id` is its own short code with no DGEEC relationship.
-- Confirmed dead; not in the algorithm.
--
-- Expected coverage (per 2026-06-09 empirical probe):
--   - 921 direct_uo_fuzzy (9ano with codigo_uo_dgeec)
--   - ~865 fuzzy_spatial (606 sec at sim>=0.6 + ~259 9ano-fallback at sim>=0.6)
--   - ~188 unmatched (~28 sec + ~133 9ano residual + small privates / IPSS)
--   - Total rows ≈ 1,974 = 661 sec + 1,313 9ano

with publico_all as (
    select eid, 'sec'::text as kind, nome, geom_3763, null::text as codigo_uo_dgeec
    from {{ ref('silver_publico_rankings_sec') }}
    union all
    select eid, '9ano'::text, nome, geom_3763, codigo_uo_dgeec
    from {{ ref('silver_publico_rankings_9ano') }}
),

-- Path 1: 9ano with codigo_uo_dgeec — UO-restricted fuzzy.
direct_uo_fuzzy as (
    select
        p.eid                                                          as publico_eid,
        p.kind,
        r.codigo_escola                                                as codigo_dgeec,
        'direct_uo_fuzzy'::text                                        as match_method,
        similarity(unaccent(lower(p.nome)), unaccent(lower(r.nome)))   as match_score,
        st_distance(p.geom_3763, r.geom_3763)                          as match_distance_m,
        row_number() over (
            partition by p.eid
            order by similarity(unaccent(lower(p.nome)), unaccent(lower(r.nome))) desc,
                     st_distance(p.geom_3763, r.geom_3763) asc
        )                                                              as rn
    from publico_all p
    join {{ ref('stg_rede_escolar') }} r
        on r.codigo_uo = p.codigo_uo_dgeec
    where p.codigo_uo_dgeec is not null
),

-- Path 2: spatial+name fuzzy, sim >= 0.6 threshold.
fuzzy_spatial as (
    select
        p.eid                                                          as publico_eid,
        p.kind,
        r.codigo_escola                                                as codigo_dgeec,
        'fuzzy_spatial'::text                                          as match_method,
        similarity(unaccent(lower(p.nome)), unaccent(lower(r.nome)))   as match_score,
        st_distance(p.geom_3763, r.geom_3763)                          as match_distance_m,
        row_number() over (
            partition by p.eid
            order by similarity(unaccent(lower(p.nome)), unaccent(lower(r.nome))) desc,
                     st_distance(p.geom_3763, r.geom_3763) asc
        )                                                              as rn
    from publico_all p
    join {{ ref('stg_rede_escolar') }} r
        on st_dwithin(p.geom_3763, r.geom_3763, 500)
),

-- Pick the best match per eid, preferring Path 1 (more authoritative)
-- over Path 2 when both produced a winner.
ranked as (
    select publico_eid, kind, codigo_dgeec, match_method, match_score, match_distance_m, 1 as method_priority
    from direct_uo_fuzzy where rn = 1
    union all
    select publico_eid, kind, codigo_dgeec, match_method, match_score, match_distance_m, 2
    from fuzzy_spatial where rn = 1 and match_score >= 0.6
),

best as (
    select *,
        row_number() over (partition by publico_eid order by method_priority asc, match_score desc) as best_rn
    from ranked
)

select
    a.eid                                                              as publico_eid,
    a.kind,
    b.codigo_dgeec,
    coalesce(b.match_method, 'unmatched')                              as match_method,
    b.match_score,
    b.match_distance_m
from publico_all a
left join (select * from best where best_rn = 1) b
    on b.publico_eid = a.eid
