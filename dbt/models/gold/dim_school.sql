{{
  config(
    materialized='table'
  )
}}

-- Canonical gold dim of every Portuguese school across all 5 levels
-- (KG → universidade), the foundation for listing_school_features
-- (per-listing nearest-school + best-score amenity scoring).
--
-- Single-table design with `school_type` discriminator + `codigo_dgeec`
-- text PK accepting both 4-digit higher-ed UO codes and 6-digit
-- basic/sec CODESCME codes. The two code spaces are disjoint
-- (length-4 vs length-6, 0 collisions verified empirically) so a
-- single PK column is safe. Resolves Open Q #5 (planning §9).
--
-- Why single table over split tables: the most common consumer query
-- ("schools near this property") is level-agnostic — a single join to
-- one table is trivial. Per-level filtering becomes a WHERE clause or
-- a per-level view; UNION across split tables would be the standing
-- cost otherwise. Per-school PK conventions remain pure: basic_sec
-- uses 6-digit codigo_escola (CODESCME); higher-ed uses 4-digit
-- codigo_unidade_organica.
--
-- Ranking signals: schools may have multiple rankings (a basic+sec
-- school has both 3º ciclo "9ano" AND secundário scores). Rather
-- than collapsing to one canonical ranking_score, we expose all three
-- as separate columns; downstream picks per use case. ~570 schools
-- have BOTH 9ano + sec rankings (escolas básicas e secundárias).
--
-- xref provenance: publico_eid + match_confidence preserved per
-- ranking so downstream can audit which Público row drove which
-- score, and filter by confidence tier (high / medium / low).
--
-- Higher-ed ranking: silver_dges_acesso_uo at fase 1 of the most
-- recent year — fase 1 is the most discriminating phase (most
-- candidates compete for the best vagas).

with

-- ──────────────────────── BASIC_SEC ROWS ─────────────────────────────
-- Picks a single best ranking per codigo_dgeec when multiple Público
-- eids map to the same DGEEC school (e.g. "Colégio Novo da Maia" has
-- two eids 800394 and 913006 both mapping to codigo_escola 800394).
-- Resolution order: highest confidence first, then most recent year.
ranked_sec as (
    select distinct on (x.codigo_dgeec)
        x.codigo_dgeec,
        x.publico_eid              as publico_eid_sec,
        x.match_confidence         as match_confidence_sec,
        s.ranking_score            as ranking_sec_score,
        s.ranking_year             as ranking_sec_year
    from {{ ref('xref_publico_dgeec') }} x
    join {{ ref('silver_publico_rankings_sec') }} s on s.eid = x.publico_eid
    where x.kind = 'sec' and x.codigo_dgeec is not null
    order by x.codigo_dgeec,
             case x.match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end,
             s.ranking_year desc
),

ranked_9ano as (
    select distinct on (x.codigo_dgeec)
        x.codigo_dgeec,
        x.publico_eid              as publico_eid_9ano,
        x.match_confidence         as match_confidence_9ano,
        s.ranking_score            as ranking_9ano_score,
        s.ranking_year             as ranking_9ano_year
    from {{ ref('xref_publico_dgeec') }} x
    join {{ ref('silver_publico_rankings_9ano') }} s on s.eid = x.publico_eid
    where x.kind = '9ano' and x.codigo_dgeec is not null
    order by x.codigo_dgeec,
             case x.match_confidence when 'high' then 1 when 'medium' then 2 when 'low' then 3 else 4 end,
             s.ranking_year desc
),

basic_sec as (
    select
        r.codigo_escola                    as codigo_dgeec,
        'basic_sec'::text                  as school_type,
        r.nome,
        r.codigo_uo                        as agrupamento_codigo,
        r.nome_uo                          as agrupamento_nome,
        null::text                         as instituicao_nome,
        r.tipologia,
        r.ciclo,
        r.natureza,
        null::text                         as natureza_tipo,
        r.distrito,
        r.concelho,
        r.morada,
        r.latitude,
        r.longitude,
        r.geom_4326,
        r.geom_3763,
        rs.ranking_sec_score,
        rs.ranking_sec_year,
        r9.ranking_9ano_score,
        r9.ranking_9ano_year,
        null::numeric                      as ranking_higher_ed_score,
        null::integer                      as ranking_higher_ed_year,
        null::integer                      as ranking_higher_ed_phase,
        rs.publico_eid_sec,
        r9.publico_eid_9ano,
        rs.match_confidence_sec,
        r9.match_confidence_9ano,
        'rede_escolar'::text               as source,
        r.source_loaded_at
    from {{ ref('stg_rede_escolar') }} r
    left join ranked_sec  rs on rs.codigo_dgeec = r.codigo_escola
    left join ranked_9ano r9 on r9.codigo_dgeec = r.codigo_escola
),

-- ──────────────────────── HIGHER_ED ROWS ─────────────────────────────
higher_ed_ranking as (
    -- Latest year, fase 1 only (most discriminating phase) per UO.
    select distinct on (codigo_unidade_organica)
        codigo_unidade_organica,
        nota_ult_colocado_weighted          as ranking_higher_ed_score,
        year                                as ranking_higher_ed_year,
        phase                               as ranking_higher_ed_phase
    from {{ ref('silver_dges_acesso_uo') }}
    where codigo_unidade_organica is not null
      and phase = 1
    order by codigo_unidade_organica, year desc
),

higher_ed as (
    select
        u.codigo_unidade_organica          as codigo_dgeec,
        'higher_ed'::text                  as school_type,
        u.unidade_organica_nome            as nome,
        null::text                         as agrupamento_codigo,
        null::text                         as agrupamento_nome,
        u.instituicao_nome,
        null::text                         as tipologia,
        null::text                         as ciclo,
        null::text                         as natureza,
        u.natureza_tipo,
        u.distrito,
        u.concelho,
        u.morada,
        u.latitude,
        u.longitude,
        u.geom_4326,
        u.geom_3763,
        null::numeric                      as ranking_sec_score,
        null::integer                      as ranking_sec_year,
        null::numeric                      as ranking_9ano_score,
        null::integer                      as ranking_9ano_year,
        h.ranking_higher_ed_score,
        h.ranking_higher_ed_year,
        h.ranking_higher_ed_phase,
        null::text                         as publico_eid_sec,
        null::text                         as publico_eid_9ano,
        null::text                         as match_confidence_sec,
        null::text                         as match_confidence_9ano,
        'dgeec_ens_sup'::text              as source,
        u.source_loaded_at
    from {{ ref('stg_dgeec_ens_sup') }} u
    left join higher_ed_ranking h on h.codigo_unidade_organica = u.codigo_unidade_organica
)

select * from basic_sec
union all
select * from higher_ed
