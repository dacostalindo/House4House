{{
  config(
    materialized='table'
  )
}}

-- Bridge table: Público school id (eid) ↔ DGEEC 6-digit school code
-- (codigo_escola). Resolves Open Q #2 from [[pt-education-amenity-pillar]].
-- One row per publico_eid; unmatched schools surface explicitly with
-- codigo_dgeec=NULL and match_method='unmatched'.
--
-- Empirical-probe-driven, 2-stage algorithm (locked 2026-06-09):
--
-- ──────────────────────────────────────────────────────────────────────
-- Stage 1 — `direct_uo_fuzzy` (9ano with `codigo_uo_dgeec` populated)
-- ──────────────────────────────────────────────────────────────────────
-- Restrict rede_escolar candidates to the school's agrupamento
-- (codigo_uo = publico.codigo_uo_dgeec), pick the best name-similarity
-- match. UO scope is sufficient evidence by itself; empirically 921/921
-- (100%) of 9ano-with-coduo resolve at avg sim=0.992. match_confidence
-- forced to 'high'.
--
-- ──────────────────────────────────────────────────────────────────────
-- Stage 2 — `ensemble` (sec + 9ano without coduo)
-- ──────────────────────────────────────────────────────────────────────
-- Candidate window = same normalized concelho (strips '(R.A.A)' /
-- '(São Miguel)' parentheticals so 'Lagoa (R.A.A)' matches 'Lagoa
-- (São Miguel)') OR within ST_DWithin(2000m). Four algorithms vote on
-- the best codigo_escola:
--   1. Trigram similarity (pg_trgm)        ≥ 0.6  → vote for top sim
--   2. Levenshtein (1 - lev/maxlen)         ≥ 0.5  → vote for top score
--   3. Jaccard token-set                    ≥ 0.3  → vote for top score
--   4. Phonetic (dmetaphone first 2 tokens) =      → binary match
--
-- Each algorithm fails in different ways (trigram is order-sensitive,
-- Levenshtein blows up on length differences, Jaccard is bag-of-words,
-- phonetic loses non-name-stem content). When ≥2 of them converge on
-- the same codigo_escola, false-positive risk drops sharply.
--
-- `match_confidence`:
--   - 'high'   = ≥3 algorithms agree (or Stage 1)
--   - 'medium' = exactly 2 algorithms agree
--   - 'unmatched' = no consensus
--
-- ──────────────────────────────────────────────────────────────────────
-- Algorithm comparison (per 2026-06-09 probe over 1,974 schools):
-- ──────────────────────────────────────────────────────────────────────
-- Single-algorithm coverage:        Ensemble coverage:
--   Trigram (sim≥0.6):    1,839       ≥1 vote:      1,924
--   Levenshtein (≥0.5):   1,894       ≥2 votes:     1,874  ← chosen
--   Jaccard (≥0.3):       1,894       ≥3 votes:     1,834
--   Phonetic:             1,893       ≥4 votes:     1,719
--
-- The id_publico ↔ DGEEC prefix probe (LEFT(codigo_escola,4) =
-- LPAD(id_publico,4)) was tested and matches 0/661 sec — dead path.

with publico_all as (
    select eid, 'sec'::text as kind, nome, concelho, geom_3763,
           null::text as codigo_uo_dgeec
    from {{ ref('silver_publico_rankings_sec') }}
    union all
    select eid, '9ano'::text, nome, concelho, geom_3763, codigo_uo_dgeec
    from {{ ref('silver_publico_rankings_9ano') }}
),

-- Helper: normalized concelho (strips parenthetical suffix like '(R.A.A)' / '(São Miguel)').
publico_normed as (
    select *,
        lower(unaccent(trim(regexp_replace(coalesce(concelho, ''), '\s*\([^)]*\)\s*$', '')))) as concelho_norm,
        unaccent(lower(nome)) as nome_norm,
        regexp_replace(unaccent(lower(nome)), '[^a-z0-9 ]', '', 'g') as nome_clean
    from publico_all
),

rede_normed as (
    select codigo_escola, codigo_uo, nome, concelho, geom_3763,
        lower(unaccent(trim(regexp_replace(coalesce(concelho, ''), '\s*\([^)]*\)\s*$', '')))) as concelho_norm,
        unaccent(lower(nome)) as nome_norm,
        regexp_replace(unaccent(lower(nome)), '[^a-z0-9 ]', '', 'g') as nome_clean
    from {{ ref('stg_rede_escolar') }}
),

-- ─── Stage 1 ─── direct_uo_fuzzy: 9ano with codigo_uo_dgeec
stage1 as (
    select p.eid as publico_eid, p.kind,
        r.codigo_escola as codigo_dgeec,
        'direct_uo_fuzzy'::text as match_method,
        'high'::text            as match_confidence,
        4                       as votes,
        similarity(p.nome_norm, r.nome_norm) as match_score,
        st_distance(p.geom_3763, r.geom_3763) as match_distance_m,
        row_number() over (
            partition by p.eid
            order by similarity(p.nome_norm, r.nome_norm) desc,
                     st_distance(p.geom_3763, r.geom_3763) asc
        ) as rn
    from publico_normed p
    join rede_normed r on r.codigo_uo = p.codigo_uo_dgeec
    where p.codigo_uo_dgeec is not null
),

-- ─── Stage 2 candidate window ───
candidates as (
    select p.eid, p.kind, p.nome_norm as p_nome, p.nome_clean as p_clean,
           p.geom_3763 as p_geom,
           r.codigo_escola, r.nome_norm as r_nome, r.nome_clean as r_clean,
           r.geom_3763 as r_geom,
           st_distance(p.geom_3763, r.geom_3763) as dist_m,
           similarity(p.nome_norm, r.nome_norm) as sim_trgm,
           levenshtein(left(p.nome_clean, 200), left(r.nome_clean, 200)) as lev,
           greatest(length(p.nome_clean), length(r.nome_clean)) as max_len,
           cardinality(array(
               select unnest(string_to_array(p.nome_clean, ' '))
               intersect
               select unnest(string_to_array(r.nome_clean, ' '))
           ))::float
             / nullif(cardinality(array(
               select unnest(string_to_array(p.nome_clean, ' '))
               union
               select unnest(string_to_array(r.nome_clean, ' '))
           )), 0) as jaccard,
           (dmetaphone(split_part(p.nome_clean, ' ', 1) || ' ' || split_part(p.nome_clean, ' ', 2)) =
            dmetaphone(split_part(r.nome_clean, ' ', 1) || ' ' || split_part(r.nome_clean, ' ', 2))
           )::int as phonetic_match
    from publico_normed p
    join rede_normed r
      on (p.concelho_norm <> '' and p.concelho_norm = r.concelho_norm)
         or st_dwithin(p.geom_3763, r.geom_3763, 2000)
    where p.eid not in (select publico_eid from stage1 where rn = 1)
),

-- Best candidate per (eid, algorithm) — one pick per algorithm per school.
trgm_pick as (
    select distinct on (eid) eid, codigo_escola, sim_trgm as score, dist_m
    from candidates where sim_trgm >= 0.6
    order by eid, sim_trgm desc, dist_m asc
),
lev_pick as (
    select distinct on (eid) eid, codigo_escola, (1.0 - (lev::float / nullif(max_len, 0))) as score, dist_m
    from candidates where max_len > 0 and (1.0 - (lev::float / max_len)) >= 0.5
    order by eid, (lev::float / nullif(max_len, 1)) asc, dist_m asc
),
jac_pick as (
    select distinct on (eid) eid, codigo_escola, jaccard as score, dist_m
    from candidates where jaccard >= 0.3
    order by eid, jaccard desc nulls last, dist_m asc
),
phon_pick as (
    select distinct on (eid) eid, codigo_escola, 1.0::float as score, dist_m
    from candidates where phonetic_match = 1
    order by eid, dist_m asc
),

-- Collect votes per eid into one row.
votes_per_eid as (
    select coalesce(t.eid, l.eid, j.eid, p.eid) as eid,
           array_remove(array[t.codigo_escola, l.codigo_escola, j.codigo_escola, p.codigo_escola], null) as picks,
           t.score as trgm_score, t.dist_m as trgm_dist
    from trgm_pick t
    full outer join lev_pick  l on l.eid = t.eid
    full outer join jac_pick  j on j.eid = coalesce(t.eid, l.eid)
    full outer join phon_pick p on p.eid = coalesce(t.eid, l.eid, j.eid)
),

ensemble as (
    select v.eid as publico_eid,
        p.kind,
        (
            select codigo_escola
            from unnest(v.picks) as codigo_escola
            group by codigo_escola
            order by count(*) desc, codigo_escola
            limit 1
        ) as codigo_dgeec,
        (
            select count(*) from unnest(v.picks) as x where x = (
                select codigo_escola from unnest(v.picks) as codigo_escola
                group by codigo_escola order by count(*) desc, codigo_escola limit 1
            )
        ) as votes,
        v.trgm_score as match_score,
        v.trgm_dist  as match_distance_m
    from votes_per_eid v
    join publico_all p on p.eid = v.eid
),

ensemble_classified as (
    select publico_eid, kind, codigo_dgeec,
        case when votes >= 3 then 'ensemble_high'
             when votes  = 2 then 'ensemble_medium'
             else 'unmatched' end as match_method,
        case when votes >= 3 then 'high'
             when votes  = 2 then 'medium'
             else null end as match_confidence,
        votes,
        match_score,
        match_distance_m
    from ensemble
),

-- Union Stage 1 winners + Stage 2 classified results.
combined as (
    select publico_eid, kind, codigo_dgeec, match_method, match_confidence,
           votes, match_score, match_distance_m
    from stage1 where rn = 1
    union all
    select publico_eid, kind, codigo_dgeec, match_method, match_confidence,
           votes, match_score, match_distance_m
    from ensemble_classified
    where match_method <> 'unmatched'
)

-- LEFT JOIN to all Público schools so unmatched surface explicitly.
select
    p.eid                                              as publico_eid,
    p.kind,
    c.codigo_dgeec,
    coalesce(c.match_method, 'unmatched')              as match_method,
    coalesce(c.match_confidence, 'unmatched')          as match_confidence,
    coalesce(c.votes, 0)                               as votes,
    c.match_score,
    c.match_distance_m
from publico_all p
left join combined c on c.publico_eid = p.eid
