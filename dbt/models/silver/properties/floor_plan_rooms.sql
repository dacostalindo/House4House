{{
    config(
        materialized='table'
    )
}}

-- Aggregated room stats from floor plan extractions.
-- Unnests the rooms JSONB into one row per room per listing,
-- then joins to dim_geography and unified_listings for segmentation.

WITH plan_rooms AS (
    SELECT
        fp.property_id,
        fp.typology,
        fp.floor_label,
        fp.total_area_m2,
        fp.num_bedrooms,
        fp.num_bathrooms,
        fp.has_terrace,
        fp.terrace_area_m2,
        fp.extraction_confidence,
        room_entry.key    AS room_name,
        room_entry.value::NUMERIC(8,2)  AS room_area_m2
    FROM {{ ref('stg_floor_plans') }} fp,
    LATERAL jsonb_each_text(fp.rooms) AS room_entry
    WHERE fp.rooms IS NOT NULL
      AND jsonb_typeof(fp.rooms) = 'object'
      AND fp.rooms != '{}'::JSONB
),

with_listing AS (
    SELECT
        pr.*,
        ul.operation_type,
        ul.condition,
        ul.property_type_group,
        ul.distrito_name,
        ul.concelho_name,
        ul.freguesia_name,
        ul.geo_key
    FROM plan_rooms pr
    LEFT JOIN {{ ref('unified_listings') }} ul
        ON pr.property_id = ul.source_listing_id
)

SELECT
    property_id,
    typology,
    floor_label,
    total_area_m2,
    num_bedrooms,
    num_bathrooms,
    has_terrace,
    terrace_area_m2,
    extraction_confidence,
    room_name,
    room_area_m2,
    operation_type,
    condition,
    property_type_group,
    distrito_name,
    concelho_name,
    freguesia_name,
    geo_key

FROM with_listing
