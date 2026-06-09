{{
  config(
    materialized='table',
    schema='silver_education'
  )
}}

-- Latest-year-per-school rollup of stg_publico_rankings_sec — one row per
-- eid, picking the most recent year that school appeared in Público's
-- ranking corpus. Per pillar decision #3 (planning §2): "Per-school média
-- total exames nacionais, latest year only (v1)." All staging columns
-- preserved; downstream gold (dim_school) will project to the lean
-- 11+2 schema.
--
-- A school that only appeared in 2018-2019 still surfaces with
-- ranking_year=2019; consumers wanting "fresh-only" filter on ranking_year.

with ranked as (
    select
        *,
        row_number() over (partition by eid order by year desc) as rn
    from {{ ref('stg_publico_rankings_sec') }}
)

select
    -- PK + ranking year
    eid,
    year                                    as ranking_year,
    -- Identity
    id_publico,
    nome,
    concelho,
    contexto_agrupamento,
    tipo,
    -- Headline scores (0-20 scale)
    media_total_exames                      as ranking_score,
    ranking_exames,
    num_provas_total,
    ranking_superacao,
    media_esperada,
    -- Per-disciplina (9 sec disciplines)
    media_matematica_a,
    num_provas_matematica_a,
    ranking_matematica_a,
    media_portugues,
    num_provas_portugues,
    ranking_portugues,
    media_bio_geo,
    num_provas_bio_geo,
    ranking_bio_geo,
    media_fq_a,
    num_provas_fq_a,
    ranking_fq_a,
    media_geografia_a,
    num_provas_geografia_a,
    ranking_geografia_a,
    media_filosofia,
    num_provas_filosofia,
    ranking_filosofia,
    media_historia_a,
    num_provas_historia_a,
    ranking_historia_a,
    media_economia_a,
    num_provas_economia_a,
    ranking_economia_a,
    media_macs,
    num_provas_macs,
    ranking_macs,
    -- Contexto
    habilitacoes_pais,
    habilitacoes_maes,
    pct_sem_ase,
    idade_media_12ano,
    pct_professores_quadros,
    -- Retenção
    taxa_retencao_ano0,
    taxa_retencao_ano1,
    taxa_retencao_ano2,
    -- Equidade
    equidade_pct_ase_3anos,
    equidade_pct_pais_3anos,
    equidade_ranking_diferenca,
    -- Geom
    latitude,
    longitude,
    geom_4326,
    geom_3763,
    -- Audit
    source_loaded_at
from ranked
where rn = 1
