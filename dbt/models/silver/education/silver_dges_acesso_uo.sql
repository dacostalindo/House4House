{{
  config(
    materialized='table',
    schema='silver_education'
  )
}}

-- Vagas-weighted nota último colocado per (UO, year, phase). NULL nota cursos
-- are excluded from BOTH numerator (sum(vagas*nota)) and denominator
-- (sum(vagas)) — pure weighted mean over cursos with actual placements.
--
-- LEFT JOIN to the latest dgeec_ens_sup snapshot. ~5% of DGES codes are not
-- in DGEEC (UOs added since DGEEC's 2023-03-15 snapshot); those rows surface
-- as unmatched_uo=true with NULL codigo_unidade_organica. There is no
-- stg_dgeec_ens_sup yet — we inline the "latest run_date" filter here as a
-- CTE.

with dgeec_latest_run as (
    select max(run_date) as run_date
    from {{ source('bronze_education', 'raw_dgeec_ens_sup') }}
),

dgeec_uo as (
    select
        d.codigo_unidade_organica,
        d.unidade_organica_nome,
        d.codigo_instituicao,
        d.instituicao_nome,
        d.natureza_tipo
    from {{ source('bronze_education', 'raw_dgeec_ens_sup') }} d
    join dgeec_latest_run r on r.run_date = d.run_date
),

per_uo_phase as (
    select
        codigo_instit,
        year,
        phase,
        -- Weighted nota: numerator AND denominator both exclude NULL-nota cursos
        sum(case when nota_ult_colocado is not null then vagas_iniciais * nota_ult_colocado end)
          / nullif(sum(case when nota_ult_colocado is not null then vagas_iniciais end), 0)
          as nota_ult_colocado_weighted,
        sum(coalesce(vagas_iniciais, 0)) as vagas_total,
        sum(coalesce(colocados, 0))      as colocados_total,
        count(distinct codigo_curso)     as n_cursos,
        count(distinct case when nota_ult_colocado is not null then codigo_curso end)
          as n_cursos_with_placement
    from {{ ref('stg_dges_acesso') }}
    group by codigo_instit, year, phase
)

select
    u.codigo_unidade_organica,
    p.codigo_instit,
    p.year,
    p.phase,
    p.nota_ult_colocado_weighted,
    p.vagas_total,
    p.colocados_total,
    p.n_cursos,
    p.n_cursos_with_placement,
    u.unidade_organica_nome,
    u.codigo_instituicao,
    u.instituicao_nome,
    u.natureza_tipo,
    (u.codigo_unidade_organica is null) as unmatched_uo
from per_uo_phase p
left join dgeec_uo u
    on u.codigo_unidade_organica = p.codigo_instit
