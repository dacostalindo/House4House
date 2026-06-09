{{
  config(
    materialized='table'
  )
}}

-- Canonical gold dim of every Portuguese school across all 5 levels
-- (KG → universidade), the foundation for listing_school_features.
--
-- Single-table design with `school_type` discriminator + `codigo_dgeec`
-- text PK accepting both 4-digit higher-ed UO codes and 6-digit
-- basic/sec CODESCME codes. Disjoint by length, 0 collisions verified.
-- Resolves Open Q #5 (planning §9).
--
-- Time-series rankings (sec/9ano/higher_ed × multiple years) live in the
-- sibling `fact_school_ranking` table. dim_school stays a current-snapshot
-- dim per Kimball conventions — joining the fact gets you any year.
--
-- Harmonization columns (so downstream queries work uniformly across
-- school_type without special-casing):
--   - `natureza_publico_privado` ('Pública' / 'Privada' / NULL) derived
--     from the raw natureza (basic_sec uses 'Redes dos ministérios' /
--     'Particular' / 'IPSS' / 'Misericórdia'; higher_ed uses 'Ensino
--     Superior {Público|Privado} - ...'). Pública/Privada is the
--     simplest universal mental model.
--   - Level flags `has_kg`, `has_basic_1..3`, `has_sec`, `has_higher_ed`
--     parsed from rede_escolar.ciclo (semicolon-separated) for basic_sec,
--     constant for higher_ed. Filtering becomes trivial: `WHERE has_sec`
--     returns all secondary-teaching schools regardless of school_type.
--     Covers the 820 basic_sec rows that have empty tipologia but
--     populated ciclo (mostly Pré-escolar/Especial/Extra-escolar).
--
-- Per-school dedup: when multiple Público eids map to the same DGEEC
-- codigo_escola (e.g. "Colégio Novo da Maia" has 2024 + 2019 eids both
-- pointing to codigo_escola 800394), pick the best xref via
-- DISTINCT ON (codigo_dgeec) ordered by (match_confidence, year DESC).
-- xref `publico_eid` + `match_confidence` columns let downstream filter
-- by confidence tier.

with

-- ──────────────────────── BASIC_SEC ROWS ─────────────────────────────
best_xref_sec as (
    select distinct on (codigo_dgeec)
        codigo_dgeec, publico_eid, match_confidence
    from {{ ref('xref_publico_dgeec') }}
    where kind = 'sec' and codigo_dgeec is not null
    order by codigo_dgeec,
             case match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end
),

best_xref_9ano as (
    select distinct on (codigo_dgeec)
        codigo_dgeec, publico_eid, match_confidence
    from {{ ref('xref_publico_dgeec') }}
    where kind = '9ano' and codigo_dgeec is not null
    order by codigo_dgeec,
             case match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end
),

basic_sec as (
    select
        r.codigo_escola                    as codigo_dgeec,
        'basic_sec'::text                  as school_type,
        r.nome,
        r.codigo_uo                        as agrupamento_codigo,
        r.nome_uo                          as agrupamento_nome,
        -- Raw category fields (transparency)
        r.tipologia,
        r.ciclo,
        r.natureza,
        -- Harmonized
        case
            when r.natureza = 'Redes dos ministérios'           then 'Pública'
            when r.natureza in ('Particular', 'IPSS ou equiparada', 'Misericórdia de Lisboa') then 'Privada'
            else null
        end                                as natureza_publico_privado,
        -- Level flags parsed from ciclo (semicolon-separated)
        position('Pré-escolar' in coalesce(r.ciclo, '')) > 0    as has_kg,
        position('1º Ciclo'    in coalesce(r.ciclo, '')) > 0    as has_basic_1,
        position('2º Ciclo'    in coalesce(r.ciclo, '')) > 0    as has_basic_2,
        position('3º Ciclo'    in coalesce(r.ciclo, '')) > 0    as has_basic_3,
        position('Secundário'  in coalesce(r.ciclo, '')) > 0    as has_sec,
        false                              as has_higher_ed,
        -- Geography
        r.distrito,
        r.concelho,
        r.morada,
        r.latitude,
        r.longitude,
        r.geom_4326,
        r.geom_3763,
        -- xref provenance (for downstream confidence-tier filtering)
        xs.publico_eid                     as publico_eid_sec,
        xs.match_confidence                as match_confidence_sec,
        x9.publico_eid                     as publico_eid_9ano,
        x9.match_confidence                as match_confidence_9ano,
        -- Audit
        'rede_escolar'::text               as source,
        r.source_loaded_at
    from {{ ref('stg_rede_escolar') }} r
    left join best_xref_sec  xs on xs.codigo_dgeec = r.codigo_escola
    left join best_xref_9ano x9 on x9.codigo_dgeec = r.codigo_escola
),

-- ──────────────────────── HIGHER_ED ROWS ─────────────────────────────
higher_ed as (
    select
        u.codigo_unidade_organica          as codigo_dgeec,
        'higher_ed'::text                  as school_type,
        u.unidade_organica_nome            as nome,
        null::text                         as agrupamento_codigo,
        null::text                         as agrupamento_nome,
        -- natureza_tipo decomposed across the existing columns so the
        -- schema is uniform with basic_sec rows (no higher-ed-only columns).
        case
            when u.natureza_tipo ilike '%Militar e Policial Universitário%' then 'Militar e Policial Universitário'
            when u.natureza_tipo ilike '%Militar e Policial Politécnico%'   then 'Militar e Policial Politécnico'
            when u.natureza_tipo ilike '%Universitário%'                     then 'Universidade'
            when u.natureza_tipo ilike '%Politécnico%'                       then 'Politécnico'
            else null
        end                                as tipologia,
        'Ensino Superior'::text            as ciclo,
        case
            when u.natureza_tipo ilike 'Ensino Superior Público%'  then 'Ensino Superior Público'
            when u.natureza_tipo ilike 'Ensino Superior Privado%' then 'Ensino Superior Privado'
            else null
        end                                as natureza,
        case
            when u.natureza_tipo ilike 'Ensino Superior Público%'  then 'Pública'
            when u.natureza_tipo ilike 'Ensino Superior Privado%' then 'Privada'
            else null
        end                                as natureza_publico_privado,
        false                              as has_kg,
        false                              as has_basic_1,
        false                              as has_basic_2,
        false                              as has_basic_3,
        false                              as has_sec,
        true                               as has_higher_ed,
        u.distrito,
        u.concelho,
        u.morada,
        u.latitude,
        u.longitude,
        u.geom_4326,
        u.geom_3763,
        null::text                         as publico_eid_sec,
        null::text                         as match_confidence_sec,
        null::text                         as publico_eid_9ano,
        null::text                         as match_confidence_9ano,
        'dgeec_ens_sup'::text              as source,
        u.source_loaded_at
    from {{ ref('stg_dgeec_ens_sup') }} u
)

select * from basic_sec
union all
select * from higher_ed
