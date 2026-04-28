-- Rollback for idealista_developments_dlt pipeline.
-- Drops the four dlt-managed bronze tables and clears dlt's load history
-- entries for this pipeline so a fresh run starts from a clean Day 0.
--
-- Run as the warehouse user (psql -U warehouse -d house4house -f this.sql).
-- Pair with: rm -rf /opt/airflow/dlt_state/idealista_developments  on the scheduler host.

BEGIN;

DROP TABLE IF EXISTS bronze_listings.idealista_development_units_state CASCADE;
DROP TABLE IF EXISTS bronze_listings.idealista_development_units       CASCADE;
DROP TABLE IF EXISTS bronze_listings.idealista_developments_state      CASCADE;
DROP TABLE IF EXISTS bronze_listings.idealista_developments            CASCADE;

-- Wipe dlt bookkeeping so the next run does not see stale schema_versions
-- or load_id rows. _dlt_pipeline_state is intentionally NOT touched at the
-- table level — dlt will recreate it on next run, and dropping it across
-- pipelines would affect zome / remax bookkeeping which share the schema.
DELETE FROM bronze_listings._dlt_loads
 WHERE pipeline_name = 'idealista_developments_facts';
DELETE FROM bronze_listings._dlt_version
 WHERE schema_name = 'idealista_developments_facts';
DELETE FROM bronze_listings._dlt_pipeline_state
 WHERE pipeline_name = 'idealista_developments_facts';

COMMIT;
