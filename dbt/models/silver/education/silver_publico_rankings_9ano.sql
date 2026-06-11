{{
  config(
    materialized='table',
    schema='silver_education'
  )
}}

-- Latest-year-per-school rollup of stg_publico_rankings_9ano — one row per
-- eid, picking the most recent year that school appeared in Público's
-- ranking corpus. Per pillar decision #3 (planning §2): "Per-school média
-- total exames nacionais, latest year only (v1)." All staging columns
-- preserved including codigo_uo_dgeec passthrough (~79% populated); the
-- 21% gap is the future silver_publico_dgeec bridge's problem.
--
-- The COVID gap (2020+2021 cancelled Provas Finais) means schools that
-- only appeared in 2018-2019 surface with ranking_year=2019; schools that
-- only appeared post-COVID surface with their first-and-only year.

with ranked as (
    select
        *,
        row_number() over (partition by eid order by year desc) as rn
    from {{ ref('stg_publico_rankings_9ano') }}
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
    codigo_uo_dgeec,
    -- Headline scores (0-5 scale for 9ano Provas Finais)
    media_total_exames                      as ranking_score,
    ranking_exames,
    num_provas_total,
    ranking_superacao,
    media_esperada,
    -- Per-disciplina (only Mat + Port tested at 9ano)
    media_matematica_a,
    num_provas_matematica_a,
    ranking_matematica_a,
    media_portugues,
    num_provas_portugues,
    ranking_portugues,
    -- Contexto
    habilitacoes_pais,
    habilitacoes_maes,
    pct_sem_ase,
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
