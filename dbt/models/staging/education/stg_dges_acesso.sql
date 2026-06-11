{{
  config(
    materialized='view',
    schema='staging_education'
  )
}}

-- 1:1 typed cleanup of raw_dges_acesso. Filters out PK-incomplete rows and
-- normalizes whitespace in name fields. NULL nota_ult_colocado is preserved
-- (silver's vagas-weighted aggregation excludes those rows from both
-- numerator and denominator).

select
    year,
    phase,
    codigo_instit,
    codigo_curso,
    trim(nome_instituicao) as nome_instituicao,
    trim(nome_curso)       as nome_curso,
    trim(grau)             as grau,
    -- Vagas / colocados (integer counts, NULL when not applicable for the phase)
    vagas_iniciais,
    vagas_recolocacao,
    colocados,
    colocados_desemp,
    colocados_sem_class,
    vaga_adic_sem_class,
    vaga_adic_autonomas,
    vaga_adic_alineas_c_e,
    -- Nota último colocado: 0-200 escala. NULL when curso had 0 colocados or sample too small.
    nota_ult_colocado,
    vagas_sobrantes,
    -- F3-only sobras-of-prior-phase columns
    sobras_2f,
    nao_matric_2f,
    nao_matric_2f_sem_class,
    sobras_retiradas,
    source_loaded_at
from {{ source('bronze_education', 'raw_dges_acesso') }}
where codigo_instit is not null
  and codigo_curso  is not null
