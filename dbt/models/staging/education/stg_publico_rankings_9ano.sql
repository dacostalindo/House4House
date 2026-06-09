{{
  config(
    materialized='view',
    schema='staging_education'
  )
}}

-- Typed view over raw_publico_rankings filtered to kind='9ano' (3º ciclo
-- Provas Finais). 1:1 typed cleanup — joins to DGEEC / CAOP land in
-- downstream silver/gold per the pillar's single-source staging
-- convention. Trimmed to ~25 canonical columns: headline scores + the
-- only 2 disciplines tested (Matemática + Português) + contexto
-- socioeconómico + retenção + prior-year carry + identity + geom.
-- Dropped from bronze: all sec-only disciplines (0% populated for 9ano),
-- all cif_* (0%), all ranking_superacao_* per-disciplina (0%),
-- equivalência cluster (sec-only), legacy y17-y20 carries.
--
-- Row filters at staging (matches PR-A's stg_rede_escolar precedent):
--   - 5/5877 bronze rows have NULL latitude
--   - 13/5877 have lat/lon outside the PT bounding box (one row has
--     `latitude=37129` — clear data error; others are scattered junk).
--     ST_Transform to 3763 (PT-TM06) refuses these as out-of-bounds.
-- Total drop: ~18 rows so not_null(geom) + ST_Transform stay green.
-- PT bounding box: lat 32-43 (Continente 36.9-42.2 + Açores 36.9-39.7 +
-- Madeira 32.4-33.1), lon -32 to -6 (Açores -31.3, Continente -9.5 to -6.2).

select
    -- PK
    year,
    eid,
    -- Identity
    id_publico,
    trim(nome)                              as nome,
    trim(concelho)                          as concelho,
    contexto_agrupamento,
    tipo,
    codigo_uo_dgeec,
    -- Headline scores (scale 0-5 for 9ano Provas Finais)
    media_total_exames,
    ranking_exames,
    num_provas_total,
    ranking_superacao,
    media_esperada,
    -- Per-disciplina (only Mat + Port have data for 9ano)
    media_matematica_a,
    num_provas_matematica_a,
    ranking_matematica_a,
    media_portugues,
    num_provas_portugues,
    ranking_portugues,
    -- Contexto socioeconómico
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
    -- Prior year
    media_ano_anterior,
    ranking_ano_anterior,
    -- Geom (dual-CRS per ADR 2026-05-10)
    latitude,
    longitude,
    st_setsrid(st_makepoint(longitude, latitude), 4326)            as geom_4326,
    st_transform(st_setsrid(st_makepoint(longitude, latitude), 4326), 3763) as geom_3763,
    -- Audit
    source_loaded_at
from {{ source('bronze_education', 'raw_publico_rankings') }}
where kind = '9ano'
  and latitude  between 32 and 43
  and longitude between -32 and -6
