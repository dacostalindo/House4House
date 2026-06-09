{{
  config(
    materialized='view',
    schema='staging_education'
  )
}}

-- Typed view over raw_rede_escolar, filtered to (a) the latest monthly
-- snapshot, (b) active schools only ('Em funcionamento' + not flagged for
-- extinction), (c) rows with non-NULL geometry. Trimmed to the canonical
-- ~15 columns that downstream gold marts use; ArcGIS-internal fields and
-- low-signal contact columns dropped (still accessible in bronze).
--
-- ~14% of the bronze rows have NULL geometry (tail pages of the ArcGIS
-- pagination); silver filters them out here so the not_null(geom_3763)
-- test in the YAML stays green.

with latest as (
    select max(run_date) as run_date
    from {{ source('bronze_education', 'raw_rede_escolar') }}
)

select
    r.codigo_escola,
    -- Agrupamento (Unidade Orgânica)
    r.codigo_uo,
    trim(r.nome_uo)                  as nome_uo,
    -- Escola identity
    trim(r.nome)                     as nome,
    r.codigo_ciclo,
    trim(r.ciclo)                    as ciclo,
    trim(r.tipologia)                as tipologia,
    trim(r.natureza_institucional_desc) as natureza,
    -- Endereço
    trim(r.morada)                   as morada,
    r.cp4,
    r.cp3,
    trim(r.localidade)               as localidade,
    r.codigo_concelho,
    trim(r.concelho)                 as concelho,
    r.codigo_distrito,
    trim(r.distrito)                 as distrito,
    -- Coordinates + dual-CRS geom (per ADR 2026-05-10)
    r.latitude,
    r.longitude,
    r.geom                           as geom_4326,
    r.geom_pt                        as geom_3763,
    -- Audit
    r.run_date,
    r.source_loaded_at
from {{ source('bronze_education', 'raw_rede_escolar') }} r
join latest l on l.run_date = r.run_date
where r.situacao_escola = 'Em funcionamento'
  and coalesce(r.flag_extinguir, 'N') <> 'S'
  and r.geom is not null
