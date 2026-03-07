SELECT
    -- Internal keys
    _property_id                    AS property_id_internal,
    _distrito                       AS distrito,
    _operation                      AS operation_type,
    _carried_forward,
    _batch_id,
    _scrape_date                    AS scrape_date,

    -- Property identifiers
    property_id,
    property_url                    AS listing_url,
    property_type                   AS property_type_raw,
    property_subtype                AS property_subtype_raw,

    -- Price
    property_price                  AS price_raw,
    price_currency_symbol,

    -- Areas
    lot_size,
    lot_size_usable,
    property_dimensions,

    -- Rooms
    bedroom_count,
    bedrooms_count,
    bathroom_count,

    -- Floor
    floor                           AS floor_raw,
    floor_description,

    -- Features / equipment (JSONB arrays)
    property_features,
    property_equipment,

    -- Images (JSONB arrays)
    property_images,
    property_image_tags,

    -- Property details
    property_condition              AS condition_raw,
    property_description,
    property_title,
    energy_certificate              AS energy_certificate_raw,

    -- Location
    address                         AS address_raw,
    location_name,
    location_hierarchy,
    latitude,
    longitude,
    country,

    -- Agency
    agency_name,
    agency_phone,
    agency_logo,

    -- Lifecycle
    modified_at,
    status                          AS listing_status,
    last_deactivated_at,
    operation                       AS operation_raw

FROM {{ source('bronze_listings', 'raw_idealista') }}
WHERE property_url IS NOT NULL
