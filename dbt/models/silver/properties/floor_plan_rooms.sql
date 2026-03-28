{{
    config(
        materialized='table'
    )
}}

-- One row per room per floor plan image.
-- Unnests the rooms JSONB, drops NULL areas, and maps room names to categories.
-- Join to unified_listings via property_id = source_listing_id for context.

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
      AND room_entry.value IS NOT NULL
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
    CASE
        WHEN room_name ~* '^(quarto|suite)' THEN 'bedroom'
        WHEN room_name ~* '^wc'             THEN 'bathroom'
        WHEN room_name ~* '^sala'           THEN 'living_room'
        WHEN room_name ~* '^cozinha'        THEN 'kitchen'
        WHEN room_name ~* '^hall'           THEN 'hallway'
        WHEN room_name ~* '^varanda'        THEN 'balcony'
        WHEN room_name ~* '^arrumos'        THEN 'storage'
        WHEN room_name ~* '^garagem'        THEN 'garage'
        WHEN room_name ~* '^escritorio'     THEN 'office'
        ELSE 'other'
    END                                     AS room_category,
    room_area_m2

FROM plan_rooms
