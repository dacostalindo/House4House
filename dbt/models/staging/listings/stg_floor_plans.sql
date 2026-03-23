-- Floor plan extractions: 1 row per plan image per property.
-- Multiple rows per property_id possible (multi-floor plans).

SELECT
    property_id,
    image_url,
    image_position,
    typology,
    floor_label,
    total_area_m2,
    rooms,
    num_bedrooms,
    num_bathrooms,
    has_terrace,
    terrace_area_m2,
    extraction_confidence,
    model_used,
    prompt_version,
    _extracted_at,
    _batch_id

FROM {{ source('bronze_listings', 'floor_plan_extractions') }}
WHERE extraction_confidence IS NOT NULL  -- filter out null returns (non-floor-plan images)
