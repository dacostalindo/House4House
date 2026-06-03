{{ config(materialized='table') }}

-- COS 2023 (Série 2) land-use nomenclature dimension — full hierarchical
-- legend (Levels 1-4) per DGT 2024 spec:
--   "Especificações técnicas da Série 2 da Carta de Uso e Ocupação do Solo
--    de Portugal Continental"
-- (https://www.dgterritorio.gov.pt/sites/default/files/documentos-publicos/
--  COS-Serie2-EspecificacoesTecnicas.pdf, Anexo 1, pp. 12-13).
--
-- Série 2 covers both COS2018v3 and COS2023v1 — 93 classes at L4 (vs 83 in
-- Série 1 / COS2018v2). The OGC API at ogcapi.dgterritorio.gov.pt/collections/
-- cos2023v1 exposes only code_l4 + label_l4_pt per feature; this dim provides
-- the missing L1/L2/L3 PT names and the English category bucket via JOIN on
-- silver_geo.land_use.land_use_code.
--
-- L1 → English category mapping (locked 2026-06-03 after the off-by-one bug
-- in the previous inline CASE was discovered + fixed):
--   1 artificial         (Territórios artificializados)
--   2 agriculture        (Agricultura)
--   3 pasture            (Pastagens)
--   4 agroforestry       (Superfícies agroflorestais — SAF)
--   5 forest             (Florestas)
--   6 shrubland          (Matos)
--   7 sparse_vegetation  (Espaços descobertos ou com pouca vegetação)
--   8 wetland            (Zonas húmidas)
--   9 water              (Massas de água superficiais — includes Oceano at 9.3.4)
--
-- Materialized as a SQL VALUES clause — 93 rows. Pattern matches
-- dim_constraint_severity / dim_property_type (no dbt-seed infra).

WITH base AS (

    SELECT * FROM (VALUES
        -- L1=1: Territórios artificializados (37 classes)
        ('1.1.1.1', '1.1.1', '1.1', '1', 'Áreas edificadas residenciais contínuas predominantemente verticais',   'Áreas edificadas residenciais contínuas',     'Áreas edificadas residenciais',           'Territórios artificializados', 'artificial'),
        ('1.1.1.2', '1.1.1', '1.1', '1', 'Áreas edificadas residenciais contínuas predominantemente horizontais', 'Áreas edificadas residenciais contínuas',     'Áreas edificadas residenciais',           'Territórios artificializados', 'artificial'),
        ('1.1.2.1', '1.1.2', '1.1', '1', 'Áreas edificadas residenciais descontínuas',                             'Áreas edificadas residenciais descontínuas',  'Áreas edificadas residenciais',           'Territórios artificializados', 'artificial'),
        ('1.1.2.2', '1.1.2', '1.1', '1', 'Áreas edificadas residenciais descontínuas esparsas',                    'Áreas edificadas residenciais descontínuas',  'Áreas edificadas residenciais',           'Territórios artificializados', 'artificial'),
        ('1.2.1.1', '1.2.1', '1.2', '1', 'Indústria e logística',                                                  'Indústria, logística, comércio e serviços',   'Áreas edificadas de atividades económicas','Territórios artificializados', 'artificial'),
        ('1.2.1.2', '1.2.1', '1.2', '1', 'Comércio e serviços',                                                    'Indústria, logística, comércio e serviços',   'Áreas edificadas de atividades económicas','Territórios artificializados', 'artificial'),
        ('1.2.2.1', '1.2.2', '1.2', '1', 'Instalações agrícolas e pecuárias',                                      'Instalações agrícolas, pecuárias',            'Áreas edificadas de atividades económicas','Territórios artificializados', 'artificial'),
        ('1.3.1.1', '1.3.1', '1.3', '1', 'Equipamentos culturais',                                                 'Equipamentos culturais',                       'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.2.1', '1.3.2', '1.3', '1', 'Equipamentos desportivos',                                               'Equipamentos de desporto e lazer',             'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.2.2', '1.3.2', '1.3', '1', 'Equipamentos de lazer',                                                  'Equipamentos de desporto e lazer',             'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.2.3', '1.3.2', '1.3', '1', 'Campos de golfe',                                                        'Equipamentos de desporto e lazer',             'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.2.4', '1.3.2', '1.3', '1', 'Parques de campismo e de caravanismo',                                   'Equipamentos de desporto e lazer',             'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.3.1', '1.3.3', '1.3', '1', 'Cemitérios',                                                             'Cemitérios',                                   'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.3.4.1', '1.3.4', '1.3', '1', 'Outros equipamentos e instalações turísticas',                           'Outros equipamentos e instalações turísticas', 'Equipamentos',                            'Territórios artificializados', 'artificial'),
        ('1.4.1.1', '1.4.1', '1.4', '1', 'Infraestruturas de produção de energia hídrica',                         'Infraestruturas de produção de energia renovável',     'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.1.2', '1.4.1', '1.4', '1', 'Infraestruturas de produção de energia solar',                           'Infraestruturas de produção de energia renovável',     'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.1.3', '1.4.1', '1.4', '1', 'Outras Infraestruturas de produção de energia renovável',                'Infraestruturas de produção de energia renovável',     'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.2.1', '1.4.2', '1.4', '1', 'Infraestruturas de produção de energia de fonte fóssil',                 'Infraestruturas de produção de energia não renovável', 'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.3.1', '1.4.3', '1.4', '1', 'Subestações e postos de transformação de energia',                       'Infraestruturas de transformação de energia',          'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.4.1', '1.4.4', '1.4', '1', 'Infraestruturas de captação e tratamento de águas para consumo',         'Infraestruturas de águas',                             'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.4.2', '1.4.4', '1.4', '1', 'Infraestruturas de drenagem e tratamento de águas residuais',            'Infraestruturas de águas',                             'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.5.1', '1.4.5', '1.4', '1', 'Aterros',                                                                'Infraestruturas de resíduos',                          'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.5.2', '1.4.5', '1.4', '1', 'Outras infraestruturas de resíduos',                                     'Infraestruturas de resíduos',                          'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.4.6.1', '1.4.6', '1.4', '1', 'Outras Infraestruturas',                                                 'Outras Infraestruturas',                               'Infraestruturas',                'Territórios artificializados', 'artificial'),
        ('1.5.1.1', '1.5.1', '1.5', '1', 'Rede rodoviária',                                                        'Redes rodoviária e ferroviária',                       'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.1.2', '1.5.1', '1.5', '1', 'Rede ferroviária',                                                       'Redes rodoviária e ferroviária',                       'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.2.1', '1.5.2', '1.5', '1', 'Terminais portuários de mar e de rio',                                   'Áreas portuárias',                                     'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.2.2', '1.5.2', '1.5', '1', 'Estaleiros navais e docas secas',                                        'Áreas portuárias',                                     'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.2.3', '1.5.2', '1.5', '1', 'Marinas e docas pesca',                                                  'Áreas portuárias',                                     'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.3.1', '1.5.3', '1.5', '1', 'Aeroportos',                                                             'Aeroportos e aeródromos',                              'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.3.2', '1.5.3', '1.5', '1', 'Aeródromos',                                                             'Aeroportos e aeródromos',                              'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.5.4.1', '1.5.4', '1.5', '1', 'Áreas de estacionamento',                                                'Áreas de estacionamento',                              'Transportes',                    'Territórios artificializados', 'artificial'),
        ('1.6.1.1', '1.6.1', '1.6', '1', 'Minas a céu aberto',                                                     'Áreas de exploração de recursos geológicos',           'Áreas de exploração de recursos geológicos', 'Territórios artificializados', 'artificial'),
        ('1.6.1.2', '1.6.1', '1.6', '1', 'Pedreiras',                                                              'Áreas de exploração de recursos geológicos',           'Áreas de exploração de recursos geológicos', 'Territórios artificializados', 'artificial'),
        ('1.7.1.1', '1.7.1', '1.7', '1', 'Vazios sem construção',                                                  'Vazios sem construção e áreas em construção',          'Vazios sem construção e áreas em construção', 'Territórios artificializados', 'artificial'),
        ('1.7.1.2', '1.7.1', '1.7', '1', 'Áreas em construção',                                                    'Vazios sem construção e áreas em construção',          'Vazios sem construção e áreas em construção', 'Territórios artificializados', 'artificial'),
        ('1.8.1.1', '1.8.1', '1.8', '1', 'Espaços verdes',                                                         'Espaços verdes',                                       'Espaços verdes',                 'Territórios artificializados', 'artificial'),
        -- L1=2: Agricultura (11 classes)
        ('2.1.1.1', '2.1.1', '2.1', '2', 'Culturas temporárias de sequeiro e regadio',                             'Culturas temporárias de sequeiro e regadio e arrozais', 'Culturas temporárias',          'Agricultura', 'agriculture'),
        ('2.1.1.2', '2.1.1', '2.1', '2', 'Arrozais',                                                               'Culturas temporárias de sequeiro e regadio e arrozais', 'Culturas temporárias',          'Agricultura', 'agriculture'),
        ('2.2.1.1', '2.2.1', '2.2', '2', 'Vinhas',                                                                 'Vinhas',                                                'Culturas permanentes',           'Agricultura', 'agriculture'),
        ('2.2.2.1', '2.2.2', '2.2', '2', 'Pomares',                                                                'Pomares',                                               'Culturas permanentes',           'Agricultura', 'agriculture'),
        ('2.2.3.1', '2.2.3', '2.2', '2', 'Olivais',                                                                'Olivais',                                               'Culturas permanentes',           'Agricultura', 'agriculture'),
        ('2.3.1.1', '2.3.1', '2.3', '2', 'Culturas temporárias e/ou pastagens melhoradas associadas a vinha',     'Culturas temporárias e/ou pastagens melhoradas associadas a culturas permanentes',     'Áreas agrícolas heterogéneas', 'Agricultura', 'agriculture'),
        ('2.3.1.2', '2.3.1', '2.3', '2', 'Culturas temporárias e/ou pastagens melhoradas associadas a pomar',     'Culturas temporárias e/ou pastagens melhoradas associadas a culturas permanentes',     'Áreas agrícolas heterogéneas', 'Agricultura', 'agriculture'),
        ('2.3.1.3', '2.3.1', '2.3', '2', 'Culturas temporárias e/ou pastagens melhoradas associadas a olival',    'Culturas temporárias e/ou pastagens melhoradas associadas a culturas permanentes',     'Áreas agrícolas heterogéneas', 'Agricultura', 'agriculture'),
        ('2.3.2.1', '2.3.2', '2.3', '2', 'Mosaicos culturais e parcelares complexos',                              'Mosaicos culturais e parcelares complexos',             'Áreas agrícolas heterogéneas',   'Agricultura', 'agriculture'),
        ('2.3.3.1', '2.3.3', '2.3', '2', 'Agricultura com espaços naturais e seminaturais',                        'Agricultura com espaços naturais e seminaturais',       'Áreas agrícolas heterogéneas',   'Agricultura', 'agriculture'),
        ('2.4.1.1', '2.4.1', '2.4', '2', 'Agricultura e viveiros protegidos',                                      'Agricultura e viveiros protegidos',                     'Agricultura e viveiros protegidos', 'Agricultura', 'agriculture'),
        -- L1=3: Pastagens (2 classes)
        ('3.1.1.1', '3.1.1', '3.1', '3', 'Pastagens melhoradas',                                                   'Pastagens melhoradas',     'Pastagens melhoradas e pastagens espontâneas', 'Pastagens', 'pasture'),
        ('3.1.2.1', '3.1.2', '3.1', '3', 'Pastagens espontâneas',                                                  'Pastagens espontâneas',    'Pastagens melhoradas e pastagens espontâneas', 'Pastagens', 'pasture'),
        -- L1=4: Superfícies agroflorestais (SAF) (12 classes)
        ('4.1.1.1', '4.1.1', '4.1', '4', 'Superfícies agrossilvícolas de sobreiro',                                'Superfícies agrossilvícolas de folhosas',  'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.1.1.2', '4.1.1', '4.1', '4', 'Superfícies agrossilvícolas de azinheira',                               'Superfícies agrossilvícolas de folhosas',  'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.1.1.3', '4.1.1', '4.1', '4', 'Superfícies agrossilvícolas de outros carvalhos',                        'Superfícies agrossilvícolas de folhosas',  'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.1.1.4', '4.1.1', '4.1', '4', 'Superfícies agrossilvícolas de outras folhosas',                         'Superfícies agrossilvícolas de folhosas',  'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.1.2.1', '4.1.2', '4.1', '4', 'Superfícies agrossilvícolas de pinheiro manso',                          'Superfícies agrossilvícolas de resinosas', 'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.1.2.2', '4.1.2', '4.1', '4', 'Superfícies agrossilvícolas de outras resinosas',                        'Superfícies agrossilvícolas de resinosas', 'Superfícies agrossilvícolas', 'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.1.1', '4.2.1', '4.2', '4', 'Superfícies silvopastoris de sobreiro',                                  'Superfícies silvopastoris de folhosas',    'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.1.2', '4.2.1', '4.2', '4', 'Superfícies silvopastoris de azinheira',                                 'Superfícies silvopastoris de folhosas',    'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.1.3', '4.2.1', '4.2', '4', 'Superfícies silvopastoris de outros carvalhos',                          'Superfícies silvopastoris de folhosas',    'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.1.4', '4.2.1', '4.2', '4', 'Superfícies silvopastoris de outras folhosas',                           'Superfícies silvopastoris de folhosas',    'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.2.1', '4.2.2', '4.2', '4', 'Superfícies silvopastoris de pinheiro manso',                            'Superfícies silvopastoris de resinosas',   'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        ('4.2.2.2', '4.2.2', '4.2', '4', 'Superfícies silvopastoris de outras resinosas',                          'Superfícies silvopastoris de resinosas',   'Superfícies silvopastoris',   'Superfícies agroflorestais (SAF)', 'agroforestry'),
        -- L1=5: Florestas (11 classes)
        ('5.1.1.1', '5.1.1', '5.1', '5', 'Florestas de sobreiro',                                                  'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.2', '5.1.1', '5.1', '5', 'Florestas de azinheira',                                                 'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.3', '5.1.1', '5.1', '5', 'Florestas de outros carvalhos',                                          'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.4', '5.1.1', '5.1', '5', 'Florestas de castanheiro',                                               'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.5', '5.1.1', '5.1', '5', 'Florestas de alfarrobeira',                                              'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.6', '5.1.1', '5.1', '5', 'Florestas de eucalipto',                                                 'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.7', '5.1.1', '5.1', '5', 'Florestas de acácias',                                                   'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.1.8', '5.1.1', '5.1', '5', 'Florestas de outras folhosas',                                           'Florestas de folhosas',  'Florestas', 'Florestas', 'forest'),
        ('5.1.2.1', '5.1.2', '5.1', '5', 'Florestas de pinheiro bravo',                                            'Florestas de resinosas', 'Florestas', 'Florestas', 'forest'),
        ('5.1.2.2', '5.1.2', '5.1', '5', 'Florestas de pinheiro manso',                                            'Florestas de resinosas', 'Florestas', 'Florestas', 'forest'),
        ('5.1.2.3', '5.1.2', '5.1', '5', 'Florestas de outras resinosas',                                          'Florestas de resinosas', 'Florestas', 'Florestas', 'forest'),
        -- L1=6: Matos (1 class)
        ('6.1.1.1', '6.1.1', '6.1', '6', 'Matos',                                                                  'Matos',                  'Matos',     'Matos',     'shrubland'),
        -- L1=7: Espaços descobertos ou com pouca vegetação (4 classes)
        ('7.1.1.1', '7.1.1', '7.1', '7', 'Praias, dunas e areais interiores',                                      'Praias, dunas e areais', 'Espaços descobertos ou com pouca vegetação', 'Espaços descobertos ou com pouca vegetação', 'sparse_vegetation'),
        ('7.1.1.2', '7.1.1', '7.1', '7', 'Praias, dunas e areais costeiros',                                       'Praias, dunas e areais', 'Espaços descobertos ou com pouca vegetação', 'Espaços descobertos ou com pouca vegetação', 'sparse_vegetation'),
        ('7.1.2.1', '7.1.2', '7.1', '7', 'Espaços rochosos',                                                       'Espaços rochosos',       'Espaços descobertos ou com pouca vegetação', 'Espaços descobertos ou com pouca vegetação', 'sparse_vegetation'),
        ('7.1.3.1', '7.1.3', '7.1', '7', 'Vegetação esparsa',                                                      'Vegetação esparsa',      'Espaços descobertos ou com pouca vegetação', 'Espaços descobertos ou com pouca vegetação', 'sparse_vegetation'),
        -- L1=8: Zonas húmidas (3 classes)
        ('8.1.1.1', '8.1.1', '8.1', '8', 'Pauis e turfeiras',                                                      'Zonas húmidas interiores', 'Zonas húmidas', 'Zonas húmidas', 'wetland'),
        ('8.1.2.1', '8.1.2', '8.1', '8', 'Sapais',                                                                 'Zonas húmidas litorais',   'Zonas húmidas', 'Zonas húmidas', 'wetland'),
        ('8.1.2.2', '8.1.2', '8.1', '8', 'Zonas entremarés',                                                       'Zonas húmidas litorais',   'Zonas húmidas', 'Zonas húmidas', 'wetland'),
        -- L1=9: Massas de água superficiais (12 classes — includes Oceano at 9.3.4.1)
        ('9.1.1.1', '9.1.1', '9.1', '9', 'Cursos de água naturais',                                                'Cursos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.1.2', '9.1.1', '9.1', '9', 'Cursos de água modificados ou artificializados',                         'Cursos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.2.1', '9.1.2', '9.1', '9', 'Lagos e lagoas interiores artificiais',                                  'Planos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.2.2', '9.1.2', '9.1', '9', 'Lagos e lagoas interiores naturais',                                     'Planos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.2.3', '9.1.2', '9.1', '9', 'Albufeiras de barragens',                                                'Planos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.2.4', '9.1.2', '9.1', '9', 'Albufeiras de represas ou de açudes',                                    'Planos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.1.2.5', '9.1.2', '9.1', '9', 'Charcas',                                                                'Planos de água',         'Massas de água interiores',           'Massas de água superficiais', 'water'),
        ('9.2.1.1', '9.2.1', '9.2', '9', 'Aquicultura',                                                            'Aquicultura',            'Aquicultura',                         'Massas de água superficiais', 'water'),
        ('9.3.1.1', '9.3.1', '9.3', '9', 'Salinas',                                                                'Salinas',                'Massas de água de transição e costeiras', 'Massas de água superficiais', 'water'),
        ('9.3.2.1', '9.3.2', '9.3', '9', 'Lagoas costeiras',                                                       'Lagoas costeiras',       'Massas de água de transição e costeiras', 'Massas de água superficiais', 'water'),
        ('9.3.3.1', '9.3.3', '9.3', '9', 'Desembocaduras fluviais',                                                'Desembocaduras fluviais','Massas de água de transição e costeiras', 'Massas de água superficiais', 'water'),
        ('9.3.4.1', '9.3.4', '9.3', '9', 'Oceano',                                                                 'Oceano',                 'Massas de água de transição e costeiras', 'Massas de água superficiais', 'water')
    ) AS t(
        code_l4,
        code_l3,
        code_l2,
        code_l1,
        label_l4_pt,
        label_l3_pt,
        label_l2_pt,
        label_l1_pt,
        category_en
    )

)

SELECT
    code_l4,
    code_l3,
    code_l2,
    code_l1,
    label_l4_pt,
    label_l3_pt,
    label_l2_pt,
    label_l1_pt,
    category_en
FROM base
