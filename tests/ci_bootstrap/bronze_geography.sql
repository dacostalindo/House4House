-- Empty bronze geography tables for CI's Tier-1 structural dbt build.
-- silver_unified_developments joins gold_analytics.dim_geography via point-in-
-- polygon for geo_key / concelho / parish resolution; dim_geography is a dbt
-- model built from these two CAOP + INE bronze sources. Stubbing the bronze
-- entry points lets dbt build the whole staging → gold chain on empty data.
--
-- Schemas mirror the live warehouse exactly so `dbt build` catches type/column
-- mismatches against the real upstream. No data inserted.

CREATE SCHEMA IF NOT EXISTS bronze_geo;
CREATE SCHEMA IF NOT EXISTS bronze_ine;

-- ── CAOP — Carta Administrativa Oficial de Portugal (freguesia polygons) ──
CREATE TABLE IF NOT EXISTS bronze_geo.raw_caop_freguesias (
    dtmnfr                  VARCHAR,
    freguesia               TEXT,
    municipio               TEXT,
    distrito_ilha           TEXT,
    nuts3_cod               VARCHAR,
    nuts3                   TEXT,
    nuts2                   TEXT,
    nuts1                   TEXT,
    area_ha                 DOUBLE PRECISION,
    perimetro_km            INTEGER,
    designacao_simplificada TEXT,
    geom                    GEOMETRY,
    _load_timestamp         TIMESTAMPTZ
);

-- ── INE BGRI — 2021 census aggregates at subsecção grain (rolled up to freguesia) ──
CREATE TABLE IF NOT EXISTS bronze_ine.raw_bgri (
    objectid                                                      INTEGER,
    bgri2021                                                      VARCHAR,
    dt21                                                          VARCHAR,
    dtmn21                                                        VARCHAR,
    dtmnfr21                                                      VARCHAR,
    dtmnfrsec21                                                   VARCHAR,
    secnum21                                                      VARCHAR,
    ssnum21                                                       VARCHAR,
    secssnum21                                                    VARCHAR,
    subseccao                                                     VARCHAR,
    nuts1                                                         VARCHAR,
    nuts2                                                         VARCHAR,
    nuts3                                                         VARCHAR,
    n_edificios_classicos                                         DOUBLE PRECISION,
    n_edificios_class_const_1_ou_2_aloj                           DOUBLE PRECISION,
    n_edificios_class_const_3_ou_mais_alojamentos                 DOUBLE PRECISION,
    n_edificios_exclusiv_resid                                    DOUBLE PRECISION,
    n_edificios_1_ou_2_pisos                                      DOUBLE PRECISION,
    n_edificios_3_ou_mais_pisos                                   DOUBLE PRECISION,
    n_edificios_constr_antes_1945                                 DOUBLE PRECISION,
    n_edificios_constr_1946_1980                                  DOUBLE PRECISION,
    n_edificios_constr_1981_2000                                  DOUBLE PRECISION,
    n_edificios_constr_2001_2010                                  DOUBLE PRECISION,
    n_edificios_constr_2011_2021                                  DOUBLE PRECISION,
    n_edificios_com_necessidades_reparacao                        DOUBLE PRECISION,
    n_alojamentos_total                                           DOUBLE PRECISION,
    n_alojamentos_familiares                                      DOUBLE PRECISION,
    n_alojamentos_fam_class_rhabitual                             DOUBLE PRECISION,
    n_alojamentos_fam_class_vagos_ou_resid_secundaria             DOUBLE PRECISION,
    n_rhabitual_acessivel_cadeiras_rodas                          DOUBLE PRECISION,
    n_rhabitual_com_estacionamento                                DOUBLE PRECISION,
    n_rhabitual_prop_ocup                                         DOUBLE PRECISION,
    n_rhabitual_arrendados                                        DOUBLE PRECISION,
    n_agregados_domesticos_privados                               DOUBLE PRECISION,
    n_adp_1_ou_2_pessoas                                          DOUBLE PRECISION,
    n_adp_3_ou_mais_pessoas                                       DOUBLE PRECISION,
    n_nucleos_familiares                                          DOUBLE PRECISION,
    n_nucleos_familiares_com_filhos_tendo_o_mais_novo_menos_de_25 DOUBLE PRECISION,
    n_individuos                                                  DOUBLE PRECISION,
    n_individuos_h                                                DOUBLE PRECISION,
    n_individuos_m                                                DOUBLE PRECISION,
    n_individuos_0_14                                             DOUBLE PRECISION,
    n_individuos_15_24                                            DOUBLE PRECISION,
    n_individuos_25_64                                            DOUBLE PRECISION,
    n_individuos_65_ou_mais                                       DOUBLE PRECISION,
    shape_length                                                  DOUBLE PRECISION,
    shape_area                                                    DOUBLE PRECISION,
    geom                                                          GEOMETRY,
    _load_timestamp                                               TIMESTAMPTZ
);
