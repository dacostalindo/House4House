{{
  config(
    materialized='table'
  )
}}

-- Time-series ranking fact across all 3 ranking signals (Público sec +
-- Público 9ano + DGES higher-ed). One row per (codigo_dgeec, kind, year,
-- phase) — `phase` is 1/2/3 for higher_ed (CNA fases) and NULL for
-- sec/9ano (single-phase rankings).
--
-- Per pillar conventions (planning §2 decision #4), historical years
-- are in scope: sec 2018-2024 (7 years), 9ano 2018-19 + 2022-24 (5
-- years; 2020+2021 cancelled due to COVID), higher_ed 2014-2025 ×
-- 3 phases (36 datasets, ~5,900 UO-year-phase rows).
--
-- Join to [[dim-school]] via codigo_dgeec for spatial + identity.
-- Trend queries become trivial:
--   SELECT codigo_dgeec, year, ranking_score FROM fact_school_ranking
--   WHERE kind='sec' AND codigo_dgeec='800394' ORDER BY year;
--
-- xref provenance (publico_eid + match_confidence) carried on sec/9ano
-- rows so downstream can audit which Público entry drove which score
-- and filter by confidence tier. Higher_ed rows have NULL provenance —
-- the bridge isn't needed because DGES codes are themselves DGEEC UO
-- codes (95.3% direct match; the 4.7% unmatched UOs surface in
-- silver_dges_acesso_uo with unmatched_uo=true and are excluded here).

with

sec_rankings as (
    select
        x.codigo_dgeec,
        'sec'::text              as kind,
        s.year,
        null::integer            as phase,
        s.media_total_exames     as ranking_score,
        s.ranking_exames         as ranking_position,
        s.num_provas_total,
        x.publico_eid,
        x.match_confidence,
        s.source_loaded_at
    from {{ ref('xref_publico_dgeec') }} x
    join {{ ref('stg_publico_rankings_sec') }} s on s.eid = x.publico_eid
    where x.kind = 'sec' and x.codigo_dgeec is not null
),

ano9_rankings as (
    select
        x.codigo_dgeec,
        '9ano'::text             as kind,
        s.year,
        null::integer            as phase,
        s.media_total_exames     as ranking_score,
        s.ranking_exames         as ranking_position,
        s.num_provas_total,
        x.publico_eid,
        x.match_confidence,
        s.source_loaded_at
    from {{ ref('xref_publico_dgeec') }} x
    join {{ ref('stg_publico_rankings_9ano') }} s on s.eid = x.publico_eid
    where x.kind = '9ano' and x.codigo_dgeec is not null
),

higher_ed_rankings as (
    select
        codigo_unidade_organica         as codigo_dgeec,
        'higher_ed'::text               as kind,
        year,
        phase,
        nota_ult_colocado_weighted      as ranking_score,
        null::integer                   as ranking_position,
        colocados_total::bigint         as num_provas_total,
        null::text                      as publico_eid,
        null::text                      as match_confidence,
        null::timestamp                 as source_loaded_at
    from {{ ref('silver_dges_acesso_uo') }}
    where codigo_unidade_organica is not null
)

-- Dedup sec/9ano: at most one row per (codigo_dgeec, kind, year) by
-- picking the best xref entry when multiple Público eids map to the same
-- DGEEC code with overlapping years.
,
sec_deduped as (
    select distinct on (codigo_dgeec, kind, year)
        codigo_dgeec, kind, year, phase, ranking_score, ranking_position,
        num_provas_total, publico_eid, match_confidence, source_loaded_at
    from sec_rankings
    order by codigo_dgeec, kind, year,
             case match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end
),

ano9_deduped as (
    select distinct on (codigo_dgeec, kind, year)
        codigo_dgeec, kind, year, phase, ranking_score, ranking_position,
        num_provas_total, publico_eid, match_confidence, source_loaded_at
    from ano9_rankings
    order by codigo_dgeec, kind, year,
             case match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end
)

select * from sec_deduped
union all select * from ano9_deduped
union all select * from higher_ed_rankings
