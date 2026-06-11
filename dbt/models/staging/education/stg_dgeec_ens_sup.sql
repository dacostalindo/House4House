{{
  config(
    materialized='view',
    schema='staging_education'
  )
}}

-- Typed view over raw_dgeec_ens_sup, filtered to the latest run_date.
-- The source is a static-ish quarterly register (321 UOs, 0% NULL geom in
-- the 2026-06-07 probe), so "latest snapshot" is what every downstream
-- consumer wants; older snapshots stay accessible in bronze.

with latest as (
    select max(run_date) as run_date
    from {{ source('bronze_education', 'raw_dgeec_ens_sup') }}
)

select
    d.codigo_unidade_organica,
    d.codigo_instituicao,
    trim(d.instituicao_nome)         as instituicao_nome,
    trim(d.unidade_organica_nome)    as unidade_organica_nome,
    trim(d.natureza_tipo)            as natureza_tipo,
    -- Endereço
    trim(d.morada)                   as morada,
    trim(d.codigo_postal)            as codigo_postal,
    trim(d.distrito)                 as distrito,
    trim(d.concelho)                 as concelho,
    -- Coordinates + dual-CRS geom (per ADR 2026-05-10)
    d.latitude,
    d.longitude,
    d.geom                           as geom_4326,
    d.geom_pt                        as geom_3763,
    -- Audit
    d.run_date,
    d.source_loaded_at
from {{ source('bronze_education', 'raw_dgeec_ens_sup') }} d
join latest l on l.run_date = d.run_date
