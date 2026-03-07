{{
    config(
        materialized='incremental',
        unique_key='source_listing_id',
        incremental_strategy='merge',
        merge_update_columns=[
            'price_eur', 'price_per_sqm_useful', 'price_per_sqm_gross',
            'useful_area_m2', 'gross_area_m2',
            'num_rooms', 'num_bathrooms', 'floor_number', 'num_floors',
            'construction_year', 'condition', 'energy_class',
            'orientation', 'heating_type', 'typology',
            'has_elevator', 'has_parking', 'has_terrace', 'has_garden', 'has_pool',
            'has_ac', 'has_storage', 'has_wardrobes', 'is_furnished', 'is_new_development',
            'property_type_key',
            'geo_key', 'freguesia_code', 'concelho_code', 'distrito_code',
            'distrito_name', 'concelho_name', 'freguesia_name',
            'address_clean', 'postal_code', 'latitude', 'longitude', 'geom', 'geom_pt',
            'last_seen_date', 'listing_age_days', 'is_active',
            'price_change_count',
            '_updated_at'
        ],
        post_hook=[
            "CREATE INDEX IF NOT EXISTS idx_ul_geom ON {{ this }} USING GIST(geom)",
            "CREATE INDEX IF NOT EXISTS idx_ul_geo_key ON {{ this }} (geo_key)",
            "CREATE INDEX IF NOT EXISTS idx_ul_op ON {{ this }} (operation_type)",
            "CREATE INDEX IF NOT EXISTS idx_ul_active ON {{ this }} (is_active) WHERE is_active",
            "CREATE INDEX IF NOT EXISTS idx_ul_hash ON {{ this }} (property_hash)",
            "CREATE INDEX IF NOT EXISTS idx_ul_src_id ON {{ this }} (source_listing_id)",
            "UPDATE {{ this }} SET is_active = FALSE WHERE is_active = TRUE AND last_seen_date < CURRENT_DATE - INTERVAL '3 days'"
        ]
    )
}}

-- Idealista listings: parse TEXT bronze → typed silver with Portuguese labels.
-- Incremental merge on source_listing_id preserves first_seen_date/initial_price.
-- Spatial join to dim_geography for geo_key; two-pass join to dim_property_type.

WITH source_data AS (
    SELECT *
    FROM {{ ref('stg_idealista') }}
    WHERE listing_url IS NOT NULL
      AND price_raw IS NOT NULL
    {% if is_incremental() %}
      -- Incremental: only freshly scraped rows newer than last run
      AND _carried_forward = FALSE
      AND scrape_date > (SELECT MAX(last_seen_date) FROM {{ this }})
    {% endif %}
),

deduplicated AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY property_id
            ORDER BY scrape_date DESC
        ) AS _rn
    FROM source_data
),

latest AS (
    SELECT * FROM deduplicated WHERE _rn = 1
),

-- Core type casting
parsed AS (
    SELECT
        property_id::VARCHAR(50)                    AS source_listing_id,
        listing_url,
        operation_type,
        property_type_raw,
        property_subtype_raw,
        scrape_date,
        listing_status,

        -- Price
        NULLIF(price_raw, '')::NUMERIC(12,2)        AS price_eur,

        -- Areas (lot_size = primary, lot_size_usable = secondary)
        NULLIF(lot_size, '')::NUMERIC(10,2)          AS useful_area_m2,
        NULLIF(lot_size_usable, '')::NUMERIC(10,2)   AS gross_area_m2,

        -- Rooms (cap outliers)
        LEAST(
            COALESCE(
                NULLIF(bedroom_count, ''),
                NULLIF(bedrooms_count, '')
            )::SMALLINT,
            15
        )                                            AS num_rooms,
        LEAST(NULLIF(bathroom_count, '')::SMALLINT, 10)
                                                     AS num_bathrooms,

        -- Floor
        CASE
            WHEN floor_raw = 'bj' THEN -1::SMALLINT
            WHEN floor_raw = 'ss' THEN -2::SMALLINT
            WHEN floor_raw = 'st' THEN 0::SMALLINT
            WHEN floor_raw = 'en' THEN 0::SMALLINT
            WHEN floor_raw ~ '^\d+$' THEN floor_raw::SMALLINT
            ELSE NULL
        END                                          AS floor_number,

        -- Condition (Portuguese labels)
        CASE condition_raw
            WHEN 'good'           THEN 'Bom estado'
            WHEN 'newdevelopment' THEN 'Novo'
            WHEN 'renew'          THEN 'Para recuperar'
            ELSE condition_raw
        END                                          AS condition,

        -- Energy class (normalize to standard codes)
        CASE energy_certificate_raw
            WHEN 'aplus'     THEN 'A+'
            WHEN 'a'         THEN 'A'
            WHEN 'b'         THEN 'B'
            WHEN 'bminus'    THEN 'B-'
            WHEN 'c'         THEN 'C'
            WHEN 'd'         THEN 'D'
            WHEN 'e'         THEN 'E'
            WHEN 'f'         THEN 'F'
            WHEN 'g'         THEN 'G'
            ELSE NULL
        END                                          AS energy_class,

        -- Location
        address_raw,
        latitude,
        longitude,

        -- JSONB arrays for feature extraction
        property_features,
        property_equipment,
        floor_description

    FROM latest
),

-- Extract structured data from property_features JSONB
with_features AS (
    SELECT
        p.*,

        -- Concatenate all feature text for regex searching
        COALESCE(property_features::TEXT, '') || ' ' ||
        COALESCE(property_equipment::TEXT, '') || ' ' ||
        COALESCE(floor_description, '')          AS _feat_text,

        -- Construction year: "Construído em 2025"
        (
            SELECT SUBSTRING(elem FROM '\d{4}')::SMALLINT
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '^Construído em \d{4}$'
            LIMIT 1
        )                                        AS construction_year,

        -- Orientation: "Orientação Sul, Este"
        (
            SELECT SUBSTRING(elem FROM 'Orientação (.+)')
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '^Orientação '
            LIMIT 1
        )                                        AS orientation,

        -- Heating type: "Aquecimento individual: Elétrico" or "Não tem aquecimento"
        (
            SELECT
                CASE
                    WHEN elem = 'Não tem aquecimento' THEN 'Sem aquecimento'
                    ELSE SUBSTRING(elem FROM 'Aquecimento (.+)')
                END
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '^(Aquecimento|Não tem aquecimento)'
            LIMIT 1
        )                                        AS heating_type,

        -- Number of floors: "2 andares"
        (
            SELECT SUBSTRING(elem FROM '(\d+) andares?')::SMALLINT
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '^\d+ andares?$'
            LIMIT 1
        )                                        AS num_floors,

        -- Gross area from features: "150 m² construídos"
        (
            SELECT SUBSTRING(elem FROM '(\d+) m² construídos')::NUMERIC(10,2)
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '\d+ m² construídos'
            LIMIT 1
        )                                        AS gross_area_feat,

        -- Useful area from features: "119 m² úteis"
        (
            SELECT SUBSTRING(elem FROM '(\d+) m² úteis')::NUMERIC(10,2)
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '\d+ m² úteis'
            LIMIT 1
        )                                        AS useful_area_feat,

        -- Typology: first element matching T\d pattern (e.g., "T3")
        (
            SELECT elem
            FROM JSONB_ARRAY_ELEMENTS_TEXT(property_features) AS elem
            WHERE elem ~ '^T\d'
            LIMIT 1
        )                                        AS typology

    FROM parsed p
),

-- Boolean feature flags + area overrides
with_flags AS (
    SELECT
        source_listing_id,
        listing_url,
        operation_type,
        property_type_raw,
        property_subtype_raw,
        scrape_date,
        listing_status,
        price_eur,

        -- Use feature-extracted areas as fallback
        COALESCE(useful_area_m2, useful_area_feat)   AS useful_area_m2,
        COALESCE(gross_area_m2, gross_area_feat)     AS gross_area_m2,

        num_rooms,
        num_bathrooms,
        floor_number,
        num_floors,
        construction_year,
        condition,
        energy_class,
        orientation,
        heating_type,
        typology,

        address_raw,
        latitude,
        longitude,

        -- Feature flags (case-insensitive regex on combined text)
        _feat_text ~* 'elevador|ascensor'                              AS has_elevator,
        _feat_text ~* 'garagem|estacionamento|parking'                 AS has_parking,
        _feat_text ~* 'terraço|varanda|balcão'                         AS has_terrace,
        _feat_text ~* 'jardim|garden'                                  AS has_garden,
        _feat_text ~* 'piscina|pool'                                   AS has_pool,
        _feat_text ~* 'ar condicionado'                                AS has_ac,
        _feat_text ~* 'arrecadação'                                    AS has_storage,
        _feat_text ~* 'roupeiros embutidos'                            AS has_wardrobes,
        _feat_text ~* 'mobilado|cozinha equipada'                      AS is_furnished,
        _feat_text ~* 'nova construção'                                AS is_new_development

    FROM with_features
),

-- Build PostGIS geometries
with_geometry AS (
    SELECT
        *,
        CASE
            WHEN latitude IS NOT NULL AND longitude IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(longitude::FLOAT, latitude::FLOAT), 4326)
        END                                      AS geom,
        CASE
            WHEN latitude IS NOT NULL AND longitude IS NOT NULL
            THEN ST_Transform(
                ST_SetSRID(ST_MakePoint(longitude::FLOAT, latitude::FLOAT), 4326),
                3763
            )
        END                                      AS geom_pt
    FROM with_flags
),

-- Spatial join to dim_geography (point-in-polygon)
with_geo AS (
    SELECT DISTINCT ON (w.source_listing_id)
        w.*,
        g.geo_key,
        g.freguesia_code,
        g.concelho_code,
        g.distrito_code,
        g.distrito_name,
        g.concelho_name,
        g.freguesia_name
    FROM with_geometry w
    LEFT JOIN {{ ref('dim_geography') }} g
        ON ST_Within(w.geom, g.freguesia_geom)
    ORDER BY w.source_listing_id, g.geo_key
),

-- Two-pass join to dim_property_type (exact match + fallback for NULL subtype)
with_type AS (
    SELECT
        w.*,
        COALESCE(exact.property_type_key, fallback.property_type_key)
                                                 AS property_type_key,
        COALESCE(exact.tipo, fallback.tipo)      AS property_type,
        COALESCE(exact.subtipo, fallback.subtipo) AS property_subtype,
        COALESCE(exact.type_group, fallback.type_group)
                                                 AS property_type_group
    FROM with_geo w
    LEFT JOIN {{ ref('dim_property_type') }} exact
        ON exact.source_type = w.property_type_raw
        AND exact.source_subtype = w.property_subtype_raw
    LEFT JOIN {{ ref('dim_property_type') }} fallback
        ON fallback.source_type = w.property_type_raw
        AND fallback.source_subtype IS NULL
),

-- Deduplication hash
with_hash AS (
    SELECT
        *,
        MD5(
            COALESCE(source_listing_id, '') || '|' ||
            COALESCE(operation_type, '') || '|' ||
            'idealista'
        )::VARCHAR(64)                           AS property_hash,

        -- Price per sqm
        CASE WHEN useful_area_m2 > 0
            THEN ROUND(price_eur / useful_area_m2, 2)
        END                                      AS price_per_sqm_useful,
        CASE WHEN gross_area_m2 > 0
            THEN ROUND(price_eur / gross_area_m2, 2)
        END                                      AS price_per_sqm_gross,

        -- Lifecycle fields
        scrape_date                              AS last_seen_date,
        CASE
            WHEN COALESCE(listing_status, 'active') != 'active' THEN FALSE
            WHEN CURRENT_DATE - scrape_date > 3 THEN FALSE
            ELSE TRUE
        END                                      AS is_active

    FROM with_type
)

SELECT
    ROW_NUMBER() OVER (
        ORDER BY h.source_listing_id
    )::BIGINT                                    AS listing_key,
    h.property_hash,

    -- Source
    'idealista'::VARCHAR(30)                     AS source,
    h.source_listing_id,
    h.listing_url,

    -- Operation
    h.operation_type,

    -- Pricing
    h.price_eur,
    h.price_per_sqm_useful,
    h.price_per_sqm_gross,

    -- Property attributes
    h.property_type_key,
    h.property_type,
    h.property_subtype,
    h.property_type_group,
    h.typology,
    h.useful_area_m2,
    h.gross_area_m2,
    h.num_rooms,
    h.num_bathrooms,
    h.floor_number,
    h.num_floors,
    h.construction_year,
    h.condition,
    h.energy_class,
    h.orientation,
    h.heating_type,

    -- Amenity flags
    h.has_elevator,
    h.has_parking,
    h.has_terrace,
    h.has_garden,
    h.has_pool,
    h.has_ac,
    h.has_storage,
    h.has_wardrobes,
    h.is_furnished,
    h.is_new_development,

    -- Geography
    h.geo_key,
    h.freguesia_code,
    h.concelho_code,
    h.distrito_code,
    h.distrito_name,
    h.concelho_name,
    h.freguesia_name,
    CASE
        WHEN gc.road IS NOT NULL
             AND h.address_raw !~ '^(Rua |Avenida |Av\.|Travessa |Largo |Praça |Alameda |Estrada |Urbanização |Beco |Calçada )'
        THEN gc.road || COALESCE(', ' || gc.house_number, '')
        ELSE h.address_raw
    END                                          AS address_clean,
    gc.postcode::VARCHAR(10)                     AS postal_code,
    h.latitude::NUMERIC(10,7),
    h.longitude::NUMERIC(10,7),
    h.geom,
    h.geom_pt,

    -- Lifecycle (SCD)
    {% if is_incremental() %}
    COALESCE(existing.first_seen_date, h.last_seen_date)
    {% else %}
    h.last_seen_date
    {% endif %}                                  AS first_seen_date,
    h.last_seen_date,
    {% if is_incremental() %}
    (h.last_seen_date - COALESCE(existing.first_seen_date, h.last_seen_date))::INTEGER
    {% else %}
    0
    {% endif %}                                  AS listing_age_days,
    h.is_active,
    {% if is_incremental() %}
    (COALESCE(existing.price_change_count, 0)
        + CASE WHEN existing.price_eur IS DISTINCT FROM h.price_eur THEN 1 ELSE 0 END
    )::SMALLINT
    {% else %}
    0::SMALLINT
    {% endif %}                                  AS price_change_count,
    {% if is_incremental() %}
    COALESCE(existing.initial_price_eur, h.price_eur)
    {% else %}
    h.price_eur
    {% endif %}                                  AS initial_price_eur,

    -- Audit
    {% if is_incremental() %}
    COALESCE(existing._created_at, NOW())
    {% else %}
    NOW()
    {% endif %}                                  AS _created_at,
    NOW()                                        AS _updated_at

FROM with_hash h
LEFT JOIN {{ source('bronze_listings', 'reverse_geocoded') }} gc
    ON h.latitude = gc.latitude
    AND h.longitude = gc.longitude
{% if is_incremental() %}
LEFT JOIN {{ this }} existing
    ON existing.source_listing_id = h.source_listing_id
{% endif %}
