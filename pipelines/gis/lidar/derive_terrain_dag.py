"""
DGT LiDAR Derive Terrain — DTM tiles → slope COGs

For each MDT-2m tile in `bronze_terrain.raw_lidar_mdt_2m_manifest`:
  1. Download GeoTIFF from MinIO
  2. Run `gdaldem slope` (output in degrees, -compute_edges, -alg Horn)
  3. Translate to Cloud-Optimized GeoTIFF (rio-cogeo) for fast windowed reads
  4. Upload derived COG to MinIO at `lidar/derived/slope_2m/{date}/tiles/{tile_id}_slope.tif`
  5. Insert one row into `bronze_terrain.derived_lidar_slope_2m_manifest`

Same tile grid as MDT manifest, ~1 sec gdaldem + 1 sec rio-cogeo per tile,
489 tiles → ~16 min wall (single-threaded). Output total ~490 MB.

WS3b's parcel_zonal_stats_dag reads this derived manifest to compute
slope_mean / slope_p90 / slope_max per parcel via tile-aware batched
windowed reads (rasterio.windows.from_bounds).
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
DERIVED_TABLE = "bronze_terrain.derived_lidar_slope_2m_manifest"
MINIO_BUCKET = "raw"
MINIO_DERIVED_PREFIX = "lidar/derived/slope_2m"


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {DERIVED_TABLE} (
    tile_id          VARCHAR(64),
    source_tile_id   VARCHAR(64),
    geom             GEOMETRY(GEOMETRY, 3763),
    minio_object     TEXT,
    file_size_bytes  BIGINT,
    derivation       VARCHAR(32),  -- 'gdaldem_slope_horn_degrees'
    _source_url      TEXT,
    _load_timestamp  TIMESTAMPTZ DEFAULT NOW()
);
"""


CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_derived_slope_2m_geom
    ON {DERIVED_TABLE} USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_derived_slope_2m_tile_id
    ON {DERIVED_TABLE} (tile_id);
"""


INSERT_SQL = f"""
INSERT INTO {DERIVED_TABLE} (
    tile_id, source_tile_id, geom, minio_object,
    file_size_bytes, derivation, _source_url
) VALUES (
    %s, %s, %s, %s, %s, %s, %s
)
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
            "Derive slope COGs from MDT-2m tiles via gdaldem. "
            "Writes to MinIO + populates bronze_terrain.derived_lidar_slope_2m_manifest."
        ),
        schedule=None,
        start_date=datetime(2026, 5, 1),
        catchup=False,
        default_args=default_args,
        max_active_runs=1,
        max_active_tasks=4,
        tags=["lidar", "raster", "derived", "slope", "gdal"],
        params={
            "limit": Param(
                default=0,
                description="Max tiles to process (0 = all). Useful for smoke tests.",
                type="integer",
            ),
        },
    )
    def lidar_derive_terrain():
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
                SELECT tile_id, minio_object, ST_AsGeoJSON(geom) AS geom_json
                FROM {SOURCE_TABLE}
                ORDER BY tile_id
            """
            if limit > 0:
                sql += f" LIMIT {limit}"
            cur.execute(sql)
            rows = [
                {"tile_id": r[0], "minio_object": r[1], "geom_json": r[2]} for r in cur.fetchall()
            ]
            cur.close()
            conn.close()
            log.info("[derive_terrain] selected %d source tiles", len(rows))
            return rows

        @task()
        def ensure_derived_table() -> None:
            """Idempotent DDL for the derived manifest table + indexes."""
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
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(CREATE_INDEXES_SQL)
            log.info("[derive_terrain] ensured table %s", DERIVED_TABLE)
            cur.close()
            conn.close()

        @task()
        def truncate_derived_table() -> None:
            """One-shot truncate before re-derivation."""
            import psycopg2
            from airflow.models import Variable

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute(f"TRUNCATE {DERIVED_TABLE}")
            conn.commit()
            cur.close()
            conn.close()
            log.info("[derive_terrain] truncated %s", DERIVED_TABLE)

        @task()
        def derive_one_tile(tile: dict) -> dict:
            """Run gdaldem slope on one MDT tile + upload + insert manifest row."""
            import psycopg2
            from airflow.models import Variable
            from minio import Minio

            tile_id = tile["tile_id"]
            source_object = tile["minio_object"]
            geom_json = tile["geom_json"]

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            tmp_dir = tempfile.mkdtemp(prefix=f"derive_{tile_id}_")
            try:
                src_path = os.path.join(tmp_dir, f"{tile_id}.tif")
                client.fget_object(MINIO_BUCKET, source_object, src_path)

                slope_raw = os.path.join(tmp_dir, f"{tile_id}_slope_raw.tif")
                slope_cog = os.path.join(tmp_dir, f"{tile_id}_slope.tif")

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

                date_str = datetime.utcnow().strftime("%Y%m%d")
                derived_object = f"{MINIO_DERIVED_PREFIX}/{date_str}/tiles/{tile_id}_slope.tif"
                client.fput_object(
                    bucket_name=MINIO_BUCKET,
                    object_name=derived_object,
                    file_path=slope_cog,
                )
                derived_size = os.path.getsize(slope_cog)
                log.info(
                    "[derive_terrain] %s -> %s (%.1f KB)",
                    tile_id,
                    derived_object,
                    derived_size / 1024,
                )

                conn = psycopg2.connect(
                    host=Variable.get("WAREHOUSE_HOST"),
                    port=int(Variable.get("WAREHOUSE_PORT")),
                    dbname=Variable.get("WAREHOUSE_DB"),
                    user=Variable.get("WAREHOUSE_USER"),
                    password=Variable.get("WAREHOUSE_PASSWORD"),
                )
                cur = conn.cursor()
                cur.execute(
                    f"""
                    INSERT INTO {DERIVED_TABLE} (
                        tile_id, source_tile_id, geom, minio_object,
                        file_size_bytes, derivation, _source_url
                    ) VALUES (
                        %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 3763),
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        f"{tile_id}_slope",
                        tile_id,
                        geom_json,
                        derived_object,
                        derived_size,
                        "gdaldem_slope_horn_degrees",
                        source_object,
                    ),
                )
                conn.commit()
                cur.close()
                conn.close()

                return {
                    "tile_id": tile_id,
                    "derived_object": derived_object,
                    "derived_size_bytes": derived_size,
                }
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        @task()
        def log_summary(results: list[dict]) -> dict:
            total_bytes = sum(r["derived_size_bytes"] for r in results)
            log.info(
                "[derive_terrain] derived %d slope tiles (%.1f MB)",
                len(results),
                total_bytes / 1000000.0,
            )
            return {"n_tiles": len(results), "total_bytes": total_bytes}

        ensure = ensure_derived_table()
        trunc = truncate_derived_table()
        tiles = list_source_tiles()
        ensure >> trunc >> tiles
        results = derive_one_tile.expand(tile=tiles)
        log_summary(results)

    return lidar_derive_terrain()


dag = _create_dag()
