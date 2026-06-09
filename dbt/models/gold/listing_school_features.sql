{{
  config(
    materialized='table',
    indexes=[
      {'columns': ['listing_hash'], 'unique': True},
    ]
  )
}}

-- Per-listing education amenity features — the end-goal Phase 2 mart of
-- the PT education pillar. One row per listing_hash, joining
-- unified_listings_residential to [[dim-school]] via PostGIS spatial
-- (EPSG:3763 for metric distances) and to [[fact-school-ranking]] for
-- latest-year ranking signal.
--
-- Features per level (kg / basic_1 / basic_2 / basic_3 / sec / higher_ed):
--   - nearest_<level>_codigo_dgeec — DGEEC code of the closest school
--     of that level within 5km (NULL beyond that — long-tail rural)
--   - nearest_<level>_distance_m   — straight-line metres
--
-- Ranking features (latest year, within 2km):
--   - best_score_2km_sec        — best Público sec ranking (media_total_exames)
--   - best_score_2km_9ano       — best Público 9º-ano ranking
--   - best_score_2km_higher_ed  — best DGES higher-ed cutoff (nota_ult_colocado_weighted,
--                                 max across phases of the latest year)
--
-- Spatial joins use ST_DWithin(geom_3763, 5000) gated by the GIST index;
-- 5km is the long-tail cap (most listings have a basic_1 school within 500m,
-- but rural listings can be 3-4km away from any sec school).

with

listings as (
    select
        listing_hash,
        geom_pt as geom_3763
    from {{ ref('unified_listings_residential') }}
    where geom_pt is not null
),

schools as (
    select
        codigo_dgeec,
        geom_3763,
        has_kg, has_basic_1, has_basic_2, has_basic_3, has_sec, has_higher_ed
    from {{ ref('dim_school') }}
    where geom_3763 is not null
),

-- ─── Latest-year ranking per (codigo_dgeec, kind) ────────────────────
latest_sec as (
    select distinct on (codigo_dgeec)
        codigo_dgeec, ranking_score
    from {{ ref('fact_school_ranking') }}
    where kind = 'sec' and ranking_score is not null
    order by codigo_dgeec, year desc
),

latest_9ano as (
    select distinct on (codigo_dgeec)
        codigo_dgeec, ranking_score
    from {{ ref('fact_school_ranking') }}
    where kind = '9ano' and ranking_score is not null
    order by codigo_dgeec, year desc
),

-- Higher_ed: latest year, best (max) across the 3 CNA phases
latest_higher_ed_year as (
    select max(year) as max_year
    from {{ ref('fact_school_ranking') }}
    where kind = 'higher_ed' and ranking_score is not null
),

latest_higher_ed as (
    select
        codigo_dgeec,
        max(ranking_score) as ranking_score
    from {{ ref('fact_school_ranking') }}, latest_higher_ed_year
    where kind = 'higher_ed'
      and year = max_year
      and ranking_score is not null
    group by codigo_dgeec
)

select
    l.listing_hash,

    -- ─── Nearest school per level (within 5km) ───────────────────────
    n_kg.codigo_dgeec       as nearest_kg_codigo_dgeec,
    n_kg.distance_m         as nearest_kg_distance_m,
    n_b1.codigo_dgeec       as nearest_basic_1_codigo_dgeec,
    n_b1.distance_m         as nearest_basic_1_distance_m,
    n_b2.codigo_dgeec       as nearest_basic_2_codigo_dgeec,
    n_b2.distance_m         as nearest_basic_2_distance_m,
    n_b3.codigo_dgeec       as nearest_basic_3_codigo_dgeec,
    n_b3.distance_m         as nearest_basic_3_distance_m,
    n_sec.codigo_dgeec      as nearest_sec_codigo_dgeec,
    n_sec.distance_m        as nearest_sec_distance_m,
    n_he.codigo_dgeec       as nearest_higher_ed_codigo_dgeec,
    n_he.distance_m         as nearest_higher_ed_distance_m,

    -- ─── Best ranking score within 2km (latest year) ─────────────────
    bs_sec.best_score       as best_score_2km_sec,
    bs_9ano.best_score      as best_score_2km_9ano,
    bs_he.best_score        as best_score_2km_higher_ed,

    now()                   as _updated_at

from listings l

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_kg and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_kg on true

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_basic_1 and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_b1 on true

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_basic_2 and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_b2 on true

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_basic_3 and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_b3 on true

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_sec and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_sec on true

left join lateral (
    select s.codigo_dgeec, st_distance(s.geom_3763, l.geom_3763) as distance_m
    from schools s
    where s.has_higher_ed and st_dwithin(s.geom_3763, l.geom_3763, 5000)
    order by s.geom_3763 <-> l.geom_3763
    limit 1
) n_he on true

-- ─── Best ranking score within 2km (latest year per kind) ────────────
left join lateral (
    select max(r.ranking_score) as best_score
    from schools s
    join latest_sec r on r.codigo_dgeec = s.codigo_dgeec
    where st_dwithin(s.geom_3763, l.geom_3763, 2000)
) bs_sec on true

left join lateral (
    select max(r.ranking_score) as best_score
    from schools s
    join latest_9ano r on r.codigo_dgeec = s.codigo_dgeec
    where st_dwithin(s.geom_3763, l.geom_3763, 2000)
) bs_9ano on true

left join lateral (
    select max(r.ranking_score) as best_score
    from schools s
    join latest_higher_ed r on r.codigo_dgeec = s.codigo_dgeec
    where st_dwithin(s.geom_3763, l.geom_3763, 2000)
) bs_he on true
