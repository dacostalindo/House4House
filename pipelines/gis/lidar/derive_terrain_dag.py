"""
DGT LiDAR Derive Terrain — DTM tiles → in-DB postgis_raster slope rasters.

For each MDT-2m tile in `bronze_terrain.raw_lidar_mdt_2m_manifest`:
  1. Download GeoTIFF from MinIO to /tmp
  2. Run `gdaldem slope` (Horn algorithm, degrees, -compute_edges)
  3. Translate to Cloud-Optimized GeoTIFF (rio-cogeo) — local /tmp only
  4. Idempotency check: skip if filename already in bronze_terrain.raster_lidar_slope_2m
  5. Read raster bytes + INSERT via ST_FromGDALRaster — single row per tile

End state per tile: one row in `bronze_terrain.raster_lidar_slope_2m` with the
raster column populated. No MinIO archive of the slope COG — derived artifact,
regenerable from MDT in ~25-40min via DAG re-run.

Sprint-09 WS4 batch 2 PR A (2026-06-03):
- Replaces the previous "write manifest table + upload to MinIO" output with a
  single in-DB postgis_raster table that `fn_assess_polygon` queries via
  `ST_Clip` + `ST_SummaryStatsAgg` for exact-per-polygon slope stats.
- Drops `bronze_terrain.derived_lidar_slope_2m_manifest` (redundant — raster
  table IS the registry; footprint derivable via ST_ConvexHull(rast)).
- Drops `parcel_zonal_stats_dag.py` + `bronze_terrain.parcel_terrain_stats`
  (pre-aggregated parcel stats no longer needed — raster path is exact).

Per-tile runtime: ~2s gdaldem + ~2s rio-cogeo + ~3s ST_FromGDALRaster INSERT.
489 tiles × ~7s × 1/4 parallelism = ~14 min wall-clock. Idempotency makes
partial reruns near-instant.

Uses Python (rasterio is implicitly available; psycopg2 + raw bytes pass
through ST_FromGDALRaster) instead of `raster2pgsql` — that CLI is not
installed in the Airflow image and adding it requires a Dockerfile rebuild.
ST_FromGDALRaster takes a BYTEA + optional SRID and returns a raster,
GDAL-reading the bytes via the same driver as raster2pgsql under the hood.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

SOURCE_TABLE = "bronze_terrain.raw_lidar_mdt_2m_manifest"
RASTER_TABLE = "bronze_terrain.raster_lidar_slope_2m"


CREATE_RASTER_TABLE_SQL = f"""
CREATE EXTENSION IF NOT EXISTS postgis_raster;

-- PostGIS 3.x ships postgis.gdal_enabled_drivers='' by default (no drivers
-- whitelisted for security). ST_FromGDALRaster needs GTiff explicitly enabled.
-- ALTER DATABASE persists across new sessions; ALTER SYSTEM would be cluster-wide.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET postgis.gdal_enabled_drivers TO ''GTiff PNG JPEG''',
        current_database()
    );
    EXECUTE format(
        'ALTER DATABASE %I SET postgis.enable_outdb_rasters TO 1',
        current_database()
    );
END $$;

CREATE TABLE IF NOT EXISTS {RASTER_TABLE} (
    rid             SERIAL PRIMARY KEY,
    rast            RASTER,
    filename        TEXT,
    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raster_lidar_slope_2m_rast
    ON {RASTER_TABLE} USING GIST(ST_ConvexHull(rast));

CREATE INDEX IF NOT EXISTS idx_raster_lidar_slope_2m_filename
    ON {RASTER_TABLE} (filename);
"""


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="lidar_derive_terrain",
        description=(
            "Derive slope rasters from MDT-2m tiles via gdaldem and load into "
            "bronze_terrain.raster_lidar_slope_2m for in-DB ST_Clip queries "
            "from gold.fn_assess_polygon."
        ),
        schedule=None,
        start_date=datetime(2026, 5, 1),
        catchup=False,
        default_args=default_args,
        max_active_runs=1,
        max_active_tasks=4,
        tags=["lidar", "raster", "derived", "slope", "gdal", "postgis-raster"],
        params={
            "limit": Param(
                default=0,
                description="Max tiles to process (0 = all). Useful for smoke tests.",
                type="integer",
            ),
            "force_rebuild": Param(
                default=False,
                description=(
                    "If true, TRUNCATE the raster table before loading "
                    "(re-derive everything). If false (default), skip-if-filename-exists "
                    "for idempotent partial reruns."
                ),
                type="boolean",
            ),
        },
    )
    def lidar_derive_terrain():
        @task()
        def ensure_raster_table(**context) -> None:
            """Idempotent DDL: install postgis_raster + create raster table + indexes."""
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(CREATE_RASTER_TABLE_SQL)
            log.info("[derive_terrain] ensured table %s + postgis_raster extension", RASTER_TABLE)

            if context["params"].get("force_rebuild"):
                cur.execute(f"TRUNCATE {RASTER_TABLE}")
                log.info("[derive_terrain] force_rebuild=True; truncated %s", RASTER_TABLE)

            cur.close()
            conn.close()

        @task()
        def list_source_tiles(**context) -> list[dict]:
            """Read source MDT manifest + return per-tile work items."""
            import psycopg2
            from airflow.models import Variable

            limit = int(context["params"].get("limit", 0))

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            sql = f"""
                SELECT tile_id, minio_object
                FROM {SOURCE_TABLE}
                ORDER BY tile_id
            """
            if limit > 0:
                sql += f" LIMIT {limit}"
            cur.execute(sql)
            rows = [{"tile_id": r[0], "minio_object": r[1]} for r in cur.fetchall()]
            cur.close()
            conn.close()
            log.info("[derive_terrain] selected %d source tiles", len(rows))
            return rows

        @task()
        def derive_one_tile(tile: dict) -> dict:
            """gdaldem slope on one MDT tile → ST_FromGDALRaster INSERT into raster table.

            Idempotent: skips if the target filename is already in the raster table.
            """
            import psycopg2
            from airflow.models import Variable
            from minio import Minio

            tile_id = tile["tile_id"]
            source_object = tile["minio_object"]
            target_filename = f"{tile_id}_slope.tif"

            # Idempotency check first — cheapest path for re-runs.
            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute(
                f"SELECT 1 FROM {RASTER_TABLE} WHERE filename = %s LIMIT 1",
                (target_filename,),
            )
            if cur.fetchone() is not None:
                cur.close()
                conn.close()
                log.info("[derive_terrain] %s already loaded — skipping", target_filename)
                return {"tile_id": tile_id, "skipped": True}

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"derive_{tile_id}_")
            try:
                src_path = os.path.join(tmp_dir, f"{tile_id}.tif")
                client.fget_object("raw", source_object, src_path)

                slope_raw = os.path.join(tmp_dir, f"{tile_id}_slope_raw.tif")
                slope_cog = os.path.join(tmp_dir, target_filename)

                subprocess.run(
                    [
                        "gdaldem",
                        "slope",
                        src_path,
                        slope_raw,
                        "-alg",
                        "Horn",
                        "-compute_edges",
                        "-of",
                        "GTiff",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )

                subprocess.run(
                    [
                        "rio",
                        "cogeo",
                        "create",
                        slope_raw,
                        slope_cog,
                        "--nodata",
                        "-9999",
                        "--cog-profile",
                        "deflate",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )

                with open(slope_cog, "rb") as f:
                    raster_bytes = f.read()

                # SET LOCAL belt-and-braces in case ALTER DATABASE didn't take
                # effect on this session (postgis.gdal_enabled_drivers default
                # is empty in PostGIS 3.x for security).
                cur.execute(
                    "SET LOCAL postgis.gdal_enabled_drivers = 'GTiff PNG JPEG'"
                )
                cur.execute(
                    f"""
                    INSERT INTO {RASTER_TABLE} (rast, filename)
                    VALUES (ST_FromGDALRaster(%s, 3763), %s)
                    """,
                    (psycopg2.Binary(raster_bytes), target_filename),
                )
                conn.commit()
                cur.close()
                conn.close()

                size_bytes = os.path.getsize(slope_cog)
                log.info(
                    "[derive_terrain] loaded %s (%.1f KB)",
                    target_filename,
                    size_bytes / 1024.0,
                )
                return {
                    "tile_id": tile_id,
                    "filename": target_filename,
                    "size_bytes": size_bytes,
                    "skipped": False,
                }
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(results: list[dict]) -> dict:
            loaded = [r for r in results if not r.get("skipped")]
            skipped = [r for r in results if r.get("skipped")]
            total_bytes = sum(r.get("size_bytes", 0) for r in loaded)
            log.info(
                "[derive_terrain] loaded %d tiles (%.1f MB), skipped %d (idempotent)",
                len(loaded),
                total_bytes / 1000000.0,
                len(skipped),
            )
            return {
                "n_loaded": len(loaded),
                "n_skipped": len(skipped),
                "total_bytes": total_bytes,
            }

        ensured = ensure_raster_table()
        tiles = list_source_tiles()
        ensured >> tiles
        results = derive_one_tile.expand(tile=tiles)
        log_summary(results)

    return lidar_derive_terrain()


dag = _create_dag()
