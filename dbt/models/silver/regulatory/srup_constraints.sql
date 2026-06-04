{{
    config(
        materialized='table',
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_srup_constraints_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_srup_constraints_geom_wgs84 ON {{ this }} USING GIST(geom_wgs84)",
            "CREATE INDEX IF NOT EXISTS idx_srup_constraints_code ON {{ this }} (constraint_code)",
            "CREATE INDEX IF NOT EXISTS idx_srup_constraints_code_zone ON {{ this }} (constraint_code, zone_type)",
            "CREATE INDEX IF NOT EXISTS idx_srup_constraints_muni ON {{ this }} (municipality_code) WHERE municipality_code IS NOT NULL"
        ]
    )
}}

-- Unified SRUP constraint silver — UNION ALL of 15 staging SRUP layers,
-- with TWO dim joins:
--   1. dim_constraint_severity → national-law severity attrs (severity 0-3,
--      authority, legal_basis, buffer_m, etc.)
--   2. dim_pdm_constraint → local-plan PDM rules where zone_pattern equals
--      the SRUP constraint_code (e.g. RAN, ZPE, Perigosidade_Incendio_Rural).
--      Aggregated as array of pdm_constraint_keys per SRUP feature.
--
-- Architecture rationale: zoning polygons are too coarse for constraint
-- resolution. SRUP features carry the actual spatially-precise constraints;
-- attaching dim references here lets fn_assess_polygon do ONE spatial JOIN
-- (input polygon ∩ srup_constraints.geom) to get severity + applicable PDM
-- rules + national legal basis all in one row.
--
-- The applies_to_zone_types filter (e.g. Perigosidade alta vs media) is
-- respected in the PDM JOIN — a SRUP feature with zone_type='perigosidade_alta'
-- only attaches PDM rules whose applies_to_zone_types contains that value.
-- The applies_when_land_classification filter is NOT applied here (we don't
-- know the polygon's classification yet); fn_assess_polygon applies it at
-- query time when combining SRUP hit with silver_geo.zoning hit.
--
-- Per-layer extension columns (DPH: area_ha+estado+...; IC: freguesias+...;
-- REN_areal: classifica+dinamica+...) are intentionally dropped here. They
-- remain accessible via the `properties` JSONB sidecar from staging.

{% set srup_layers = [
    'stg_srup_ran',
    'stg_srup_ren_areal',
    'stg_srup_ren_linear',
    'stg_srup_ic',
    'stg_srup_dph',
    'stg_srup_zpe',
    'stg_srup_zec',
    'stg_srup_areas_protegidas',
    'stg_srup_rede_viaria',
    'stg_srup_rede_eletrica',
    'stg_srup_rede_ferroviaria',
    'stg_srup_albufeiras',
    'stg_srup_defesa_militar',
    'stg_srup_aeronautica',
    'stg_srup_perigosidade_inc_rural'
] %}

WITH srup_union AS (

    {%- for layer in srup_layers %}
    SELECT
        '{{ layer }}'::TEXT     AS source_layer,
        feature_id,
        constraint_code,
        zone_type,
        designation,
        restriction_type,
        typology,
        law_type,
        restriction_law,
        dr_reference,
        restriction_date,
        restriction_url,
        municipality,
        properties,
        geom,
        geom_wgs84,
        _source_url,
        _load_timestamp
    FROM {{ ref(layer) }}
    {%- if not loop.last %}
    UNION ALL
    {%- endif %}
    {%- endfor %}

)

SELECT
    ROW_NUMBER() OVER (ORDER BY u.constraint_code, u.zone_type, u.feature_id)::BIGINT
                                                                AS srup_constraint_key,
    u.source_layer,
    u.feature_id,

    -- shared SRUP contract
    u.constraint_code,
    u.zone_type,
    u.designation,
    u.restriction_type,
    u.typology,
    u.law_type,
    u.restriction_law,
    u.dr_reference,
    CASE WHEN u.restriction_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         THEN u.restriction_date::DATE
         ELSE NULL END                                            AS restriction_date,
    u.restriction_url,
    UPPER(TRIM(u.municipality))                                   AS municipality_text,
    muni.municipality_codes,
    muni.municipality_codes[1]                                    AS municipality_code,
    muni.municipality_names_resolved                              AS municipality_names,

    -- severity attrs DENORMALIZED from dim_constraint_severity
    -- (national-law layer — joins by constraint_code + zone_type)
    sev.severity,
    sev.severity_label,
    sev.category,
    sev.buffer_m,
    sev.buffer_ref,
    sev.legal_basis,
    sev.requires_prior_opinion,
    sev.authority,
    sev.is_hard_gate,
    sev.is_conditioned,
    sev.is_advisory,
    sev.display_color,

    -- PDM linkage DENORMALIZED from dim_pdm_constraint
    -- (local-plan layer — joins by municipality_code + zone_pattern=constraint_code,
    --  with applies_to_zone_types filter respected)
    pdm.pdm_constraint_keys,
    pdm.pdm_rule_count,
    pdm.pdm_articles,
    pdm.pdm_constraint_types,

    -- raw properties (kept for per-layer extensions / debugging)
    u.properties,

    -- spatial
    ST_GeometryType(u.geom)                                       AS geom_type,
    CASE WHEN ST_GeometryType(u.geom) IN ('ST_Polygon','ST_MultiPolygon')
         THEN ROUND((ST_Area(u.geom) / 10000.0)::NUMERIC, 2)
         ELSE NULL END                                            AS area_ha,
    u.geom,
    u.geom_wgs84,

    -- audit
    u._source_url,
    u._load_timestamp,
    NOW()                                                         AS _updated_at

FROM srup_union u
LEFT JOIN LATERAL (
    -- Multi-município resolution: SRUP municipality_text is sometimes a
    -- comma-separated list (e.g. "VAGOS, AVEIRO, OVAR, ..."). Split on
    -- comma, trim, resolve each to a concelho_code via dim_geography.
    -- Empty array when no name resolves (national-scope features).
    SELECT
        COALESCE(ARRAY_AGG(g.concelho_code ORDER BY g.concelho_code) FILTER (WHERE g.concelho_code IS NOT NULL), '{}'::TEXT[]) AS municipality_codes,
        COALESCE(ARRAY_AGG(g.concelho_name ORDER BY g.concelho_code) FILTER (WHERE g.concelho_name IS NOT NULL), '{}'::TEXT[]) AS municipality_names_resolved
    FROM unnest(string_to_array(COALESCE(u.municipality, ''), ',')) AS m_raw
    LEFT JOIN (
        SELECT DISTINCT concelho_code, concelho_name FROM {{ ref('dim_geography') }}
    ) g ON UPPER(TRIM(g.concelho_name)) = UPPER(TRIM(m_raw))
)                                       muni ON TRUE
LEFT JOIN {{ ref('dim_constraint_severity') }} sev
    ON sev.constraint_code = u.constraint_code
   AND sev.zone_type      = u.zone_type
LEFT JOIN LATERAL (
    -- For each SRUP feature, aggregate matching PDM rules across all
    -- municípios the feature touches. Match condition:
    --   - município_code ∈ feature's municipality_codes
    --   - AND (zone_pattern equals constraint_code directly
    --          OR constraint_code is in the zone_pattern's cross_refs_srup
    --             — picks up rules from subcategoria/local-overlay patterns
    --             that invoke this SRUP layer, e.g. Esp. Florestal Proteção
    --             rules attach to REN/ZPE features via the xref)
    --   - AND (applies_to_zone_types NULL OR includes this feature's zone_type)
    SELECT
        ARRAY_AGG(d.pdm_constraint_key ORDER BY d.pdm_constraint_key) AS pdm_constraint_keys,
        COUNT(*)::INTEGER                                              AS pdm_rule_count,
        ARRAY_AGG(DISTINCT d.legal_article  ORDER BY d.legal_article)  AS pdm_articles,
        ARRAY_AGG(DISTINCT d.constraint_type ORDER BY d.constraint_type) AS pdm_constraint_types
    FROM {{ ref('dim_pdm_constraint') }} d
    WHERE d.municipality_code = ANY(muni.municipality_codes)
      AND u.constraint_code = ANY(d.zone_pattern)
      -- zone_pattern is now TEXT[] containing primary pattern + any SRUP
      -- layer cross-refs. Single = ANY check replaces the prior dual match
      -- (zone_pattern direct OR in cross_refs_srup).
      AND (
          d.applies_to_zone_types IS NULL
          OR u.zone_type = ANY(d.applies_to_zone_types)
      )
)                                       pdm ON TRUE
