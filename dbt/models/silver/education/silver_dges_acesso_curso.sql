{{
  config(
    materialized='table',
    schema='silver_education'
  )
}}

-- Per-curso grain: (codigo_unidade_organica, year, phase, codigo_curso).
-- Sibling to silver_dges_acesso_uo (UO-level rollup). Keeps the
-- denormalised names (nome_curso, nome_instituicao, grau) that the UO
-- rollup has to drop. LEFT JOIN to stg_dgeec_ens_sup on codigo_instit;
-- ~5% of DGES codes have no DGEEC match (UOs added since DGEEC's snapshot)
-- and surface as unmatched_uo=true with NULL codigo_unidade_organica.

select
    u.codigo_unidade_organica,
    d.codigo_instit,
    d.codigo_curso,
    d.year,
    d.phase,
    d.nome_curso,
    d.nome_instituicao,
    d.grau,
    -- Vagas / colocados / nota (preserved as-is from stg)
    d.vagas_iniciais,
    d.vagas_recolocacao,
    d.colocados,
    d.colocados_desemp,
    d.colocados_sem_class,
    d.nota_ult_colocado,
    d.vagas_sobrantes,
    -- DGEEC-side denormalised fields (NULL when unmatched)
    u.instituicao_nome      as instituicao_nome_dgeec,
    u.unidade_organica_nome,
    u.natureza_tipo,
    (u.codigo_unidade_organica is null) as unmatched_uo
from {{ ref('stg_dges_acesso') }} d
left join {{ ref('stg_dgeec_ens_sup') }} u
    on u.codigo_unidade_organica = d.codigo_instit
