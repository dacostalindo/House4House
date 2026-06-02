{{ config(materialized='table') }}

-- SRUP constraint severity dimension — maps (constraint_code, zone_type) to a
-- 0-3 construction-severity, the managing authority, and the legal basis.
-- Queried by gold.fn_assess_polygon (sprint-09) after each per-layer ST_Intersects.
--
-- Severity scale (see wiki/concepts/srup-constraint-model.md):
--   3 = hard gate    — construction prohibited as a rule (an exception path
--                      exists but the default answer is "no")
--   2 = conditioned  — construction possible only with a prior favourable
--                      opinion / authorization from the managing authority
--   1 = advisory     — regime largely inapplicable or minor
--   0 = no constraint
--
-- zone_type is a per-feature attribute carried by each stg_srup_* model
-- (derived from servidao / tipologia / geometry type) — NOT a geometric
-- core-vs-buffer computation. Each of the 14 constraint layers has 1-3
-- zone_types.
--
-- buffer_m + buffer_ref tell fn_assess_polygon how to space-test the layer:
--   buffer_ref = 'geom' — buffer the stored geometry directly by buffer_m.
--                         0 where the polygon already IS the legal servidao;
--                         10 for REN_linear watercourse lines (10 m margem,
--                         DL 166/2008); 10 for active/station rede_ferroviaria
--                         — the polygon is the ~20 m zone (10 m each side of
--                         track, DL 276/2003 art. 15/1), the +10 m covers the
--                         art. 15/2 height-growth rule.
--   buffer_ref = 'axis' — buffer_m is the legal distance FROM THE ROAD AXIS
--                         (Lei 34/2015 art. 32); the bronze geom is the road
--                         corridor polygon, not the axis, so fn_assess_polygon
--                         subtracts the per-feature half-width
--                         (~ST_Area/ST_Perimeter) before buffering.
--                         RedeViaria only.
--
-- Materialized as a SQL VALUES clause — 27 rows. Pattern matches
-- dim_property_type / ref_imi_rates / ref_imt_brackets (no dbt-seed infra).

WITH base AS (

    SELECT * FROM (VALUES
        ('RAN',             'reserva_agricola',             3, 'agricultural',   0,  'geom', 'DL 73/2009 art. 21-23 (am. DL 199/2015)',    TRUE,  'Entidade Regional da RAN'),
        ('REN_areal',       'reserva_ecologica',            3, 'ecological',     0,  'geom', 'DL 166/2008 art. 20-22 (am. DL 124/2019)',   TRUE,  'CCDR'),
        ('REN_areal',       'exclusao',                     0, 'ecological',     0,  'geom', 'DL 166/2008 (am. DL 124/2019)',              FALSE, 'n/a'),
        ('REN_linear',      'linha_de_agua',                3, 'ecological',     10, 'geom', 'DL 166/2008 art. 20 (am. DL 124/2019)',      TRUE,  'CCDR'),
        ('IC',              'monumento',                    3, 'heritage',       0,  'geom', 'Lei 107/2001 art. 45 + DL 309/2009',         TRUE,  'DGPC / Direcao Regional de Cultura'),
        ('IC',              'zona_protecao',                2, 'heritage',       0,  'geom', 'Lei 107/2001 art. 43 + DL 309/2009 art. 51', TRUE,  'DGPC / Direcao Regional de Cultura'),
        ('DPH',             'non_aedificandi',              3, 'water_domain',   0,  'geom', 'Lei 54/2005 art. 25',                        TRUE,  'APA'),
        ('DPH',             'ocupacao_condicionada',        2, 'water_domain',   0,  'geom', 'Lei 54/2005 art. 25',                        TRUE,  'APA'),
        ('ZPE',             'rede_natura',                  2, 'conservation',   0,  'geom', 'DL 140/99 art. 9-10',                        TRUE,  'ICNF / CCDR'),
        ('ZEC',             'rede_natura',                  2, 'conservation',   0,  'geom', 'DL 140/99 art. 9-10',                        TRUE,  'ICNF / CCDR'),
        ('AreasProtegidas', 'area_protegida',               3, 'conservation',   0,  'geom', 'DL 142/2008 art. 23',                        TRUE,  'ICNF'),
        ('RedeViaria',      'servidao_rodoviaria_ip',       2, 'infrastructure', 50, 'axis', 'Lei 34/2015 art. 32',                        TRUE,  'Infraestruturas de Portugal'),
        ('RedeViaria',      'servidao_rodoviaria_ic',       2, 'infrastructure', 35, 'axis', 'Lei 34/2015 art. 32',                        TRUE,  'Infraestruturas de Portugal'),
        ('RedeViaria',      'servidao_rodoviaria_local',    2, 'infrastructure', 20, 'axis', 'Lei 34/2015 art. 32',                        TRUE,  'Infraestruturas de Portugal / municipio'),
        ('RedeEletrica',    'servidao_eletrica_at',         2, 'infrastructure', 0,  'geom', 'DL 43335 + RSLEAT (DR 1/92) art. 30',        TRUE,  'E-Redes'),
        ('RedeEletrica',    'servidao_eletrica_mat',        2, 'infrastructure', 0,  'geom', 'DL 43335 + RSLEAT (DR 1/92) art. 30',        TRUE,  'REN'),
        ('RedeFerroviaria', 'servidao_ferroviaria_ativa',   3, 'infrastructure', 10, 'geom', 'DL 276/2003 art. 15',                        TRUE,  'Infraestruturas de Portugal'),
        ('RedeFerroviaria', 'servidao_ferroviaria_inativa', 1, 'infrastructure', 0,  'geom', 'DL 276/2003 art. 15',                        FALSE, 'Infraestruturas de Portugal'),
        ('RedeFerroviaria', 'servidao_ferroviaria_estacao', 3, 'infrastructure', 10, 'geom', 'DL 276/2003 art. 15',                        TRUE,  'Infraestruturas de Portugal'),
        ('Albufeiras',      'protegida',                    3, 'water_domain',   0,  'geom', 'DL 107/2009 art. 19-21',                     TRUE,  'APA / ARH'),
        ('Albufeiras',      'condicionada',                 2, 'water_domain',   0,  'geom', 'DL 107/2009 art. 19-20',                     TRUE,  'APA / ARH'),
        ('Albufeiras',      'livre',                        2, 'water_domain',   0,  'geom', 'DL 107/2009 art. 12-13',                     TRUE,  'APA / ARH'),
        ('DefesaMilitar',   'nucleo',                       3, 'military',       0,  'geom', 'Lei 2078/1955 + DL 45986/1964',              TRUE,  'Ministerio da Defesa Nacional'),
        ('DefesaMilitar',   'zona_protecao',                2, 'military',       0,  'geom', 'Lei 2078/1955 + DL 45986/1964',              TRUE,  'Ministerio da Defesa Nacional'),
        ('Aeronautica',     'area_desobstrucao',            3, 'aviation',       0,  'geom', 'DL 45987/1964',                              TRUE,  'ANAC / Forca Aerea'),
        ('Aeronautica',     'servidao',                     2, 'aviation',       0,  'geom', 'DL 45987/1964',                              TRUE,  'ANAC / Forca Aerea'),
        ('Aeronautica',     'zona_protecao',                2, 'aviation',       0,  'geom', 'DL 45987/1964',                              TRUE,  'ANAC / Forca Aerea'),
        -- ARPSI EU Floods Directive scope (sprint-09 WS4 quick-wins batch). T100=hard
        -- (PT non-aedificandi default per DL 115/2010); T1000=conditioned (catastrophe
        -- band, buildable with APA mitigation per PT planning practice).
        ('ARPSI_Floodplain', 'T100',                        3, 'flood_risk',     0,  'geom', 'Diretiva 2007/60/CE; DL 115/2010 (PGRI)',    TRUE,  'APA / ARH'),
        ('ARPSI_Floodplain', 'T1000',                       2, 'flood_risk',     0,  'geom', 'Diretiva 2007/60/CE; DL 115/2010 (PGRI)',    TRUE,  'APA / ARH')
    ) AS t(
        constraint_code,
        zone_type,
        severity,
        category,
        buffer_m,
        buffer_ref,
        legal_basis,
        requires_prior_opinion,
        authority
    )

)

SELECT
    ROW_NUMBER() OVER (ORDER BY constraint_code, zone_type)::INTEGER
                                            AS constraint_severity_key,
    constraint_code,
    zone_type,
    severity,
    category,
    buffer_m,
    buffer_ref,
    legal_basis,
    requires_prior_opinion,
    authority,
    (severity >= 3)                         AS is_hard_gate,
    (severity = 2)                          AS is_conditioned,
    (severity = 1)                          AS is_advisory,
    CASE severity
        WHEN 3 THEN 'Hard gate'
        WHEN 2 THEN 'Conditioned'
        WHEN 1 THEN 'Advisory'
        ELSE 'No constraint'
    END                                     AS severity_label,
    CASE severity
        WHEN 3 THEN '#d32f2f'
        WHEN 2 THEN '#f57c00'
        WHEN 1 THEN '#fbc02d'
        ELSE '#9e9e9e'
    END                                     AS display_color
FROM base
