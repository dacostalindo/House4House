-- Thin passthrough: 1 row per property_id already in bronze.
-- No aggregation needed since image_classifications stores 1 row per property.

SELECT
    property_id,
    image_urls,
    image_tags,
    is_render,
    render_confidence,
    condition_label,
    condition_confidence,
    finish_quality,
    finish_quality_confidence,
    model_used,
    prompt_version,
    _classified_at,
    _batch_id

FROM {{ source('bronze_listings', 'image_classifications') }}
