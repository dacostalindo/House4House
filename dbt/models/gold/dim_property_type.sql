{{ config(materialized='table') }}

-- Static dimension mapping Idealista raw property_type + property_subtype
-- to standardized Portuguese labels. ~16 rows.

SELECT * FROM (VALUES
    (1,  'flat',         NULL,                'Apartamento',     NULL,                'Apartamento'),
    (2,  'flat',         'studio',            'Apartamento',     'Estúdio',           'Apartamento'),
    (3,  'flat',         'duplex',            'Apartamento',     'Duplex',            'Apartamento'),
    (4,  'flat',         'penthouse',         'Apartamento',     'Penthouse',         'Apartamento'),
    (5,  'flat',         'loft',              'Apartamento',     'Loft',              'Apartamento'),
    (6,  'chalet',       NULL,                'Moradia',         NULL,                'Moradia'),
    (7,  'chalet',       'independantHouse',  'Moradia',         'Independente',      'Moradia'),
    (8,  'chalet',       'semidetachedHouse', 'Moradia',         'Geminada',          'Moradia'),
    (9,  'chalet',       'terracedHouse',     'Moradia',         'Em Banda',          'Moradia'),
    (10, 'chalet',       'andarMoradia',      'Moradia',         'Andar de Moradia',  'Moradia'),
    (11, 'countryHouse', NULL,                'Moradia Rústica', NULL,                'Moradia'),
    (12, 'countryHouse', 'quinta',            'Moradia Rústica', 'Quinta',            'Moradia'),
    (13, 'countryHouse', 'monteAlentejano',   'Moradia Rústica', 'Monte Alentejano',  'Moradia'),
    (14, 'countryHouse', 'casaDePueblo',      'Moradia Rústica', 'Casa de Aldeia',    'Moradia'),
    (15, 'countryHouse', 'palacio',           'Moradia Rústica', 'Palácio',           'Moradia'),
    (16, 'homes',        NULL,                'Habitação',       NULL,                'Moradia')
) AS t(property_type_key, source_type, source_subtype, tipo, subtipo, type_group)
