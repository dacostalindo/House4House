{{
  config(
    materialized='view',
    schema='staging_education'
  )
}}

-- Typed view over raw_publico_rankings filtered to kind='sec' (secundário
-- exames nacionais). 1:1 typed cleanup — joins to DGEEC / CAOP land in
-- downstream silver/gold per the pillar's single-source staging
-- convention. Trimmed to ~35 canonical columns: headline scores + 9
-- disciplines × (média, num_provas, ranking) + contexto socioeconómico
-- + retenção + equidade + prior-year carry + identity + geom.
-- Dropped from bronze: codigo_uo_dgeec (0% for sec — join uses fuzzy
-- nome+concelho+geom in silver), cif_* (only ~39% populated, low signal
-- per the bronze YAML), per-disciplina ranking_superacao_* (low signal),
-- equivalência cluster (small subset of schools), legacy y17-y20 carries
-- (semantics drift across vintages per the bronze YAML).
--
-- 0/4411 bronze rows have NULL latitude → no row drops needed.

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
    -- Headline scores (scale 0-20 for sec)
    media_total_exames,
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
    -- Contexto socioeconómico
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
where kind = 'sec'
