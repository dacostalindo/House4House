-- House4House Data Warehouse — Schema Initialisation
-- Runs once on first container start via docker-entrypoint-initdb.d.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Bronze layer — raw, source-faithful
CREATE SCHEMA IF NOT EXISTS bronze_ine;
CREATE SCHEMA IF NOT EXISTS bronze_geo;
CREATE SCHEMA IF NOT EXISTS bronze_listings;
CREATE SCHEMA IF NOT EXISTS bronze_macro;
CREATE SCHEMA IF NOT EXISTS bronze_tourism;
CREATE SCHEMA IF NOT EXISTS bronze_location;
CREATE SCHEMA IF NOT EXISTS bronze_regulatory;

-- Silver layer — cleaned, conformed
CREATE SCHEMA IF NOT EXISTS silver_properties;
CREATE SCHEMA IF NOT EXISTS silver_geo;
CREATE SCHEMA IF NOT EXISTS silver_location;
CREATE SCHEMA IF NOT EXISTS silver_market;
CREATE SCHEMA IF NOT EXISTS silver_ref;

-- Gold layer — analytical models, dimensions, facts
CREATE SCHEMA IF NOT EXISTS gold_analytics;
CREATE SCHEMA IF NOT EXISTS gold_reporting;

-- Metadata
CREATE SCHEMA IF NOT EXISTS metadata;
