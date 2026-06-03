-- Empty bronze_terrain tables for CI's Tier-1 structural dbt build.
-- Schemas mirror the live warehouse exactly. No data inserted.
--
-- Sprint-09 WS4 PR A (2026-06-03): replaced `derived_lidar_slope_2m_manifest`
-- + `parcel_terrain_stats` with the new `raster_lidar_slope_2m` postgis_raster
-- table. fn_assess_polygon queries the raster table directly via ST_Clip +
-- ST_SummaryStatsAgg.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;

CREATE SCHEMA IF NOT EXISTS bronze_terrain;

-- MDT (Digital Terrain Model) tile manifest — pointers to MinIO COGs
CREATE TABLE IF NOT EXISTS bronze_terrain.raw_lidar_mdt_2m_manifest (
    tile_id            VARCHAR(64),
    collection_id      VARCHAR(32),
    geom               GEOMETRY(GEOMETRY, 3763),
    minio_object       TEXT,
    acquisition_date   TIMESTAMPTZ,
    version            INTEGER,
    file_size_bytes    BIGINT,
    pixel_type         VARCHAR(16),
    nodata_value       DOUBLE PRECISION,
    _source_url        TEXT,
    _load_timestamp    TIMESTAMPTZ DEFAULT NOW()
);

-- MDS (Digital Surface Model) tile manifest — same shape
CREATE TABLE IF NOT EXISTS bronze_terrain.raw_lidar_mds_2m_manifest (
    LIKE bronze_terrain.raw_lidar_mdt_2m_manifest
);

-- In-DB postgis_raster table — derived slope rasters (queried by fn_assess_polygon)
CREATE TABLE IF NOT EXISTS bronze_terrain.raster_lidar_slope_2m (
    rid             SERIAL PRIMARY KEY,
    rast            RASTER,
    filename        TEXT,
    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
);
