{{ config(materialized='table') }}

-- IMT (Imposto Municipal sobre Transmissões Onerosas de Imóveis)
-- Progressive transfer tax brackets for property purchases in Portugal.
-- Source: Autoridade Tributária, valid from 1 January 2025.
-- Flat-rate brackets (648k+ primary, 621k+ secondary) have NULL max_value.

SELECT * FROM (VALUES
    -- habitação própria e permanente (primary residence)
    (1,  'primary_residence',  0.00,       104261.00,   0.0000, 0.00,      2025),
    (2,  'primary_residence',  104261.00,  142618.00,   0.0200, 2085.22,   2025),
    (3,  'primary_residence',  142618.00,  194458.00,   0.0500, 6363.76,   2025),
    (4,  'primary_residence',  194458.00,  324058.00,   0.0700, 10252.92,  2025),
    (5,  'primary_residence',  324058.00,  648022.00,   0.0800, 13493.50,  2025),
    (6,  'primary_residence',  648022.00,  1128287.00,  0.0600, 0.00,      2025),
    (7,  'primary_residence',  1128287.00, NULL,        0.0750, 0.00,      2025),
    -- habitação secundária / arrendamento (secondary residence / rental / investment)
    (8,  'secondary',          0.00,       104261.00,   0.0100, 0.00,      2025),
    (9,  'secondary',          104261.00,  142618.00,   0.0200, 1042.61,   2025),
    (10, 'secondary',          142618.00,  194458.00,   0.0500, 5321.15,   2025),
    (11, 'secondary',          194458.00,  324058.00,   0.0700, 9210.31,   2025),
    (12, 'secondary',          324058.00,  621501.00,   0.0800, 12450.89,  2025),
    (13, 'secondary',          621501.00,  1128287.00,  0.0600, 0.00,      2025),
    (14, 'secondary',          1128287.00, NULL,        0.0750, 0.00,      2025),
    -- other urban (non-housing) — flat rate
    (15, 'other_urban',        0.00,       NULL,        0.0650, 0.00,      2025),
    -- rural — flat rate
    (16, 'rural',              0.00,       NULL,        0.0500, 0.00,      2025)
) AS t(
    bracket_id,
    bracket_type,
    min_value,
    max_value,
    rate,
    deduction,
    valid_year
)
