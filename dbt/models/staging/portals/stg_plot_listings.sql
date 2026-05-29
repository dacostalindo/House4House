-- Typed staging view over bronze_listings.idealista_plots, scoped to the
-- Aveiro + Coimbra concelhos for sprint-09 Slice C (LLM plot extraction v1).
-- 403 active rows at plan time (81 Aveiro + 322 Coimbra, 2026-05-28).
--
-- Wedge demo lives in Aveiro + Coimbra concelhos; v1.5 expands to their
-- distritos, v2 goes national. See plan
-- /Users/manuellindo/.claude/plans/wobbly-kindling-hopcroft.md.
--
-- Filters:
--   - SCD2 active rows (_dlt_valid_to IS NULL)
--   - property_description IS NOT NULL (extraction needs prose)
--   - location_name in the Aveiro / Coimbra concelho freguesia set
--
-- Derived:
--   - concelho_slug ∈ {'aveiro','coimbra'} for downstream stratification +
--     per-concelho QA in silver_plot_listings_enriched.
--
-- DISTINCT ON guard: defensive against the dlt SCD2 close-row miss documented
-- in PR-B1 (stg_portal_developments_remax). Keeps a single active row per
-- listing_id even if bronze has duplicates.

WITH aveiro_filter AS (
    SELECT *
    FROM {{ source('bronze_listings', 'idealista_plots') }}
    WHERE _dlt_valid_to IS NULL
      AND property_description IS NOT NULL
      AND (
          location_name = 'Aveiro'
          OR location_name IN (
              'Aradas, Aveiro',
              'Cacia, Aveiro',
              'Esgueira, Aveiro',
              'Glória e Vera Cruz, Aveiro',
              'Oliveirinha, Aveiro',
              'Requeixo, Nossa Senhora de Fátima e Nariz, Aveiro',
              'Santa Joana, Aveiro',
              'São Bernardo, Aveiro',
              'São Jacinto, Aveiro'
          )
      )
),

coimbra_filter AS (
    SELECT *
    FROM {{ source('bronze_listings', 'idealista_plots') }}
    WHERE _dlt_valid_to IS NULL
      AND property_description IS NOT NULL
      AND (
          location_name = 'Coimbra'
          OR location_name IN (
              'Cidade de Coimbra, Coimbra',
              'Assafarge e Antanhol, Coimbra',
              'Santo António dos Olivais, Coimbra',
              'Santa Clara e Castelo Viegas, Coimbra',
              'São Martinho do Bispo e Ribeira de Frades, Coimbra',
              'Eiras e São Paulo de Frades, Coimbra',
              'Antuzede e Vil de Matos, Coimbra',
              'Taveiro - Ameal - Arzila, Coimbra',
              'Almalaguês, Coimbra',
              'Torres do Mondego, Coimbra',
              'Cernache, Coimbra',
              'Souselas e Botão, Coimbra',
              'Ceira, Coimbra',
              'Trouxemil e Torre de Vilela, Coimbra',
              'São Silvestre, Coimbra',
              'São Martinho de Árvore e Lamarosa, Coimbra',
              'Brasfemes, Coimbra',
              'São João do Campo, Coimbra'
          )
      )
),

tagged AS (
    SELECT 'aveiro'::TEXT AS concelho_slug, * FROM aveiro_filter
    UNION ALL
    SELECT 'coimbra'::TEXT AS concelho_slug, * FROM coimbra_filter
),

active_latest AS (
    SELECT DISTINCT ON (external_listing_id) *
    FROM tagged
    WHERE external_listing_id IS NOT NULL
    ORDER BY external_listing_id, _dlt_valid_from DESC
)

SELECT
    external_listing_id                                          AS listing_id,
    concelho_slug,
    property_description                                         AS description,
    property_url                                                 AS listing_url,
    property_subtype,
    lot_size,
    property_price,
    location_name,
    CASE
        WHEN latitude IS NOT NULL AND longitude IS NOT NULL
        THEN ST_Transform(
            ST_SetSRID(
                ST_MakePoint(longitude::FLOAT, latitude::FLOAT),
                4326
            ),
            3763
        )
    END                                                          AS geom_3763,
    CASE
        WHEN latitude IS NOT NULL AND longitude IS NOT NULL
        THEN ST_SetSRID(
            ST_MakePoint(longitude::FLOAT, latitude::FLOAT),
            4326
        )
    END                                                          AS geom_4326,
    NOW()::TIMESTAMPTZ                                           AS _loaded_at
FROM active_latest
