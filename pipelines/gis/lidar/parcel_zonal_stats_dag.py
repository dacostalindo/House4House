"""
LiDAR Parcel Zonal Stats — slope + elevation per polygon

Tile-aware batched zonal stats: for each LiDAR tile, OPEN ONCE, then
process all parcels intersecting that tile in a single pass via
rasterio.windows.from_bounds. This is the canonical antidote to the
naive "for each parcel, open every overlapping COG" anti-pattern that
balloons cold I/O on large parcel universes.

INPUT MODES (DAG `mode` param):
  bulk    — process every parcel in `bronze_regulatory.raw_bupi` for
            Aveiro município (concelho='Aveiro'). Truncate+rebuild
            `bronze_terrain.parcel_terrain_stats`.
  polygon — process a single ad-hoc polygon WKT (DAG param `polygon_wkt`),
            return the result via Airflow XCom for the Streamlit Draw
            mode endpoint to fetch. Does NOT write to the bulk table.

OUTPUT (bulk mode):
  bronze_terrain.parcel_terrain_stats(
    parcel_id BIGINT,
    snapshot_date DATE,
    n_pixels INTEGER,           -- valid pixels in the polygon
    elevation_mean_m DOUBLE PRECISION,
    elevation_min_m DOUBLE PRECISION,
    elevation_max_m DOUBLE PRECISION,
    elevation_range_m DOUBLE PRECISION,
    slope_mean_deg DOUBLE PRECISION,
    slope_p50_deg DOUBLE PRECISION,
    slope_p90_deg DOUBLE PRECISION,
    slope_max_deg DOUBLE PRECISION,
    _source_url TEXT,
    _load_timestamp TIMESTAMPTZ DEFAULT NOW()
  )

DTM source: bronze_terrain.raw_lidar_mdt_2m_manifest
SLOPE source: bronze_terrain.derived_lidar_slope_2m_manifest (from
              derive_terrain_dag — degrees, gdaldem Horn algorithm)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

PARCEL_TABLE = "bronze_regulatory.raw_bupi"
DTM_MANIFEST = "bronze_terrain.raw_lidar_mdt_2m_manifest"
SLOPE_MANIFEST = "bronze_terrain.derived_lidar_slope_2m_manifest"
STATS_TABLE = "bronze_terrain.parcel_terrain_stats"
MINIO_BUCKET = "raw"


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {STATS_TABLE} (
    parcel_id           BIGINT,
    snapshot_date       DATE,
    n_pixels            INTEGER,
    elevation_mean_m    DOUBLE PRECISION,
    elevation_min_m     DOUBLE PRECISION,
    elevation_max_m     DOUBLE PRECISION,
    elevation_range_m   DOUBLE PRECISION,
    slope_mean_deg      DOUBLE PRECISION,
    slope_p50_deg       DOUBLE PRECISION,
    slope_p90_deg       DOUBLE PRECISION,
    slope_max_deg       DOUBLE PRECISION,
    _source_url         TEXT,
    _load_timestamp     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parcel_id, snapshot_date)
);
"""


CREATE_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_parcel_terrain_stats_parcel
    ON {STATS_TABLE} (parcel_id);
"""


def _zonal_stats_for_tile(
    tile_object: str, parcels: list[dict], minio_client, band_role: str
) -> dict[int, dict]:
    """For one tile + a list of parcels intersecting it, return a dict
    parcel_id -> {n_pixels, mean, min, max, p50, p90} for the requested band.
    Uses a SINGLE rasterio.open() per tile.

    Each parcel dict has keys: parcel_id, geom_geojson (PT-TM06).
    band_role is 'elevation' or 'slope' — only affects key naming downstream.
    """
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from shapely.geometry import mapping, shape

    tmp_path = tempfile.mktemp(suffix=".tif")
    minio_client.fget_object(MINIO_BUCKET, tile_object, tmp_path)
    try:
        out: dict[int, dict] = {}
        with rasterio.open(tmp_path) as src:
            nd = src.nodata if src.nodata is not None else -999
            for p in parcels:
                pgeom = shape(json.loads(p["geom_geojson"]))
                bounds = pgeom.bounds  # (minx, miny, maxx, maxy) in tile CRS
                tb = src.bounds
                bx_min = max(bounds[0], tb.left)
                bx_max = min(bounds[2], tb.right)
                by_min = max(bounds[1], tb.bottom)
                by_max = min(bounds[3], tb.top)
                if bx_min >= bx_max or by_min >= by_max:
                    continue
                window = from_bounds(bx_min, by_min, bx_max, by_max, transform=src.transform)
                window = window.round_offsets().round_lengths()
                if window.width <= 0 or window.height <= 0:
                    continue
                arr = src.read(1, window=window)
                if arr.size == 0:
                    continue
                tx = src.window_transform(window)
                mask = geometry_mask(
                    [mapping(pgeom)],
                    out_shape=arr.shape,
                    transform=tx,
                    invert=True,
                )
                vals = arr[mask & (arr != nd)]
                if vals.size == 0:
                    continue
                out[int(p["parcel_id"])] = {
                    "n_pixels": int(vals.size),
                    "mean": float(np.mean(vals)),
                    "min": float(np.min(vals)),
                    "max": float(np.max(vals)),
                    "p50": float(np.percentile(vals, 50)),
                    "p90": float(np.percentile(vals, 90)),
                }
        return out
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _push_parcels_temp_table(cur, parcels: list[dict]) -> None:
    cur.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS _zs_parcels (
            parcel_id BIGINT,
            geom GEOMETRY(GEOMETRY, 3763)
        );
        TRUNCATE _zs_parcels;
        """
    )
    for p in parcels:
        cur.execute(
            "INSERT INTO _zs_parcels(parcel_id, geom) "
            "VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 3763))",
            (p["parcel_id"], p["geom_geojson"]),
        )


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    }

    @dag(
        dag_id="lidar_parcel_zonal_stats",
        description=(
            "Tile-aware batched zonal stats from LiDAR DTM + slope rasters. "
            "Bulk mode rebuilds bronze_terrain.parcel_terrain_stats for Aveiro "
            "BUPI parcels; polygon mode returns ad-hoc result via XCom for "
            "Streamlit Draw mode."
        ),
        schedule=None,
        start_date=datetime(2026, 5, 1),
        catchup=False,
        default_args=default_args,
        max_active_runs=1,
        max_active_tasks=4,
        tags=["lidar", "raster", "zonal_stats", "parcels"],
        params={
            "mode": Param(
                default="bulk",
                description="bulk = all Aveiro BUPI parcels; polygon = ad-hoc WKT",
                enum=["bulk", "polygon"],
            ),
            "polygon_wkt": Param(
                default="",
                description="Polygon WKT in EPSG:3763 (only used when mode=polygon)",
                type="string",
            ),
            "polygon_id": Param(
                default=-1,
                description="Identifier for ad-hoc polygon (echoed back in result)",
                type="integer",
            ),
        },
    )
    def lidar_parcel_zonal_stats():
        @task()
        def collect_parcels(**context) -> list[dict]:
            """Return list of {parcel_id, geom_geojson} for the chosen mode."""
            import psycopg2
            from airflow.models import Variable

            mode = context["params"].get("mode", "bulk")
            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            if mode == "bulk":
                cur.execute(
                    f"""
                    SELECT processoid, ST_AsGeoJSON(geom)
                    FROM {PARCEL_TABLE}
                    WHERE concelho ILIKE 'Aveiro' AND geom IS NOT NULL
                """
                )
                rows = cur.fetchall()
                out = [{"parcel_id": r[0], "geom_geojson": r[1]} for r in rows]
                log.info("[zonal_stats] bulk: %d Aveiro BUPI parcels", len(out))
            else:
                wkt = context["params"].get("polygon_wkt", "").strip()
                pid = int(context["params"].get("polygon_id", -1))
                if not wkt:
                    raise ValueError("polygon mode requires polygon_wkt param")
                cur.execute(
                    "SELECT ST_AsGeoJSON(ST_SetSRID(ST_GeomFromText(%s), 3763))",
                    (wkt,),
                )
                geom_json = cur.fetchone()[0]
                out = [{"parcel_id": pid, "geom_geojson": geom_json}]
                log.info("[zonal_stats] polygon mode: pid=%d", pid)

            cur.close()
            conn.close()
            return out

        @task()
        def map_parcels_to_dtm_tiles(parcels: list[dict]) -> list[dict]:
            """Per DTM tile, list intersecting parcels (clipped to tile)."""
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
            _push_parcels_temp_table(cur, parcels)
            cur.execute(
                f"""
                SELECT t.minio_object, p.parcel_id, ST_AsGeoJSON(ST_Intersection(p.geom, t.geom))
                FROM {DTM_MANIFEST} t
                JOIN _zs_parcels p ON ST_Intersects(t.geom, p.geom)
            """
            )
            pairs = cur.fetchall()
            cur.close()
            conn.close()

            grouped: dict[str, list[dict]] = defaultdict(list)
            for tile_obj, pid, gj in pairs:
                grouped[tile_obj].append({"parcel_id": pid, "geom_geojson": gj})

            log.info(
                "[zonal_stats] DTM tile-parcel pairs=%d, distinct tiles=%d",
                len(pairs),
                len(grouped),
            )
            return [{"tile_object": k, "parcels": v} for k, v in grouped.items()]

        @task()
        def map_parcels_to_slope_tiles(parcels: list[dict]) -> list[dict]:
            """Per slope tile, list intersecting parcels (clipped to tile)."""
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
            _push_parcels_temp_table(cur, parcels)
            cur.execute(
                f"""
                SELECT t.minio_object, p.parcel_id, ST_AsGeoJSON(ST_Intersection(p.geom, t.geom))
                FROM {SLOPE_MANIFEST} t
                JOIN _zs_parcels p ON ST_Intersects(t.geom, p.geom)
            """
            )
            pairs = cur.fetchall()
            cur.close()
            conn.close()

            grouped: dict[str, list[dict]] = defaultdict(list)
            for tile_obj, pid, gj in pairs:
                grouped[tile_obj].append({"parcel_id": pid, "geom_geojson": gj})

            log.info(
                "[zonal_stats] slope tile-parcel pairs=%d, distinct tiles=%d",
                len(pairs),
                len(grouped),
            )
            return [{"tile_object": k, "parcels": v} for k, v in grouped.items()]

        @task()
        def stats_for_dtm_tile(work_item: dict) -> dict:
            """Open one DTM tile, batch-stat all overlapping parcels.
            Returns {'results': {parcel_id_str: {...}}} so Airflow doesn't
            treat the parcel-id-keyed dict as multiple_outputs (which would
            require string keys)."""
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            inner = _zonal_stats_for_tile(
                work_item["tile_object"], work_item["parcels"], client, "elevation"
            )
            return {"results": {str(k): v for k, v in inner.items()}}

        @task()
        def stats_for_slope_tile(work_item: dict) -> dict:
            from airflow.models import Variable
            from minio import Minio

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            inner = _zonal_stats_for_tile(
                work_item["tile_object"], work_item["parcels"], client, "slope"
            )
            return {"results": {str(k): v for k, v in inner.items()}}

        @task()
        def aggregate_per_parcel(dtm_results: list[dict], slope_results: list[dict]) -> list[dict]:
            """Combine per-tile per-parcel results into one record per parcel.
            When a parcel spans multiple tiles, weighted-average the means by
            n_pixels and recompute extrema as min/max across parts.
            """
            elev_acc: dict[int, dict] = defaultdict(
                lambda: {
                    "wsum": 0.0,
                    "wn": 0,
                    "min": float("inf"),
                    "max": float("-inf"),
                }
            )
            slope_acc: dict[int, dict] = defaultdict(
                lambda: {
                    "wsum_mean": 0.0,
                    "wn": 0,
                    "max_p50": float("-inf"),
                    "max_p90": float("-inf"),
                    "max_max": float("-inf"),
                }
            )
            envelope: dict[int, int] = defaultdict(int)

            for e in dtm_results:
                for pid_str, s in e.get("results", {}).items():
                    pid = int(pid_str)
                    n = s["n_pixels"]
                    elev_acc[pid]["wsum"] += s["mean"] * n
                    elev_acc[pid]["wn"] += n
                    elev_acc[pid]["min"] = min(elev_acc[pid]["min"], s["min"])
                    elev_acc[pid]["max"] = max(elev_acc[pid]["max"], s["max"])
                    envelope[pid] += n

            for e in slope_results:
                for pid_str, s in e.get("results", {}).items():
                    pid = int(pid_str)
                    n = s["n_pixels"]
                    slope_acc[pid]["wsum_mean"] += s["mean"] * n
                    slope_acc[pid]["wn"] += n
                    slope_acc[pid]["max_p50"] = max(slope_acc[pid]["max_p50"], s["p50"])
                    slope_acc[pid]["max_p90"] = max(slope_acc[pid]["max_p90"], s["p90"])
                    slope_acc[pid]["max_max"] = max(slope_acc[pid]["max_max"], s["max"])

            out: list[dict] = []
            all_pids = set(elev_acc.keys()) | set(slope_acc.keys())
            for pid in all_pids:
                e = elev_acc[pid]
                s = slope_acc[pid]
                row = {
                    "parcel_id": pid,
                    "n_pixels": envelope[pid],
                    "elevation_mean_m": (e["wsum"] / e["wn"]) if e["wn"] else None,
                    "elevation_min_m": e["min"] if e["wn"] else None,
                    "elevation_max_m": e["max"] if e["wn"] else None,
                    "elevation_range_m": (e["max"] - e["min"]) if e["wn"] else None,
                    "slope_mean_deg": (s["wsum_mean"] / s["wn"]) if s["wn"] else None,
                    "slope_p50_deg": s["max_p50"] if s["wn"] else None,
                    "slope_p90_deg": s["max_p90"] if s["wn"] else None,
                    "slope_max_deg": s["max_max"] if s["wn"] else None,
                }
                out.append(row)

            log.info("[zonal_stats] aggregated %d parcel rows", len(out))
            return out

        @task()
        def write_results(rows: list[dict], **context) -> dict:
            """In bulk mode: TRUNCATE+INSERT into parcel_terrain_stats.
            In polygon mode: skip DB write, return rows in XCom for caller."""
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable

            mode = context["params"].get("mode", "bulk")
            if mode == "polygon":
                log.info("[zonal_stats] polygon mode — skipping DB write")
                return {"mode": "polygon", "rows": rows}

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
            cur.execute(f"TRUNCATE {STATS_TABLE}")

            today = date.today()
            tuples = [
                (
                    r["parcel_id"],
                    today,
                    r["n_pixels"],
                    r["elevation_mean_m"],
                    r["elevation_min_m"],
                    r["elevation_max_m"],
                    r["elevation_range_m"],
                    r["slope_mean_deg"],
                    r["slope_p50_deg"],
                    r["slope_p90_deg"],
                    r["slope_max_deg"],
                    "lidar_parcel_zonal_stats",
                )
                for r in rows
            ]
            insert_sql = f"""
                INSERT INTO {STATS_TABLE} (
                    parcel_id, snapshot_date, n_pixels,
                    elevation_mean_m, elevation_min_m, elevation_max_m, elevation_range_m,
                    slope_mean_deg, slope_p50_deg, slope_p90_deg, slope_max_deg,
                    _source_url
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
            psycopg2.extras.execute_batch(cur, insert_sql, tuples, page_size=500)
            cur.close()
            conn.close()
            log.info("[zonal_stats] wrote %d rows to %s", len(rows), STATS_TABLE)
            return {"mode": "bulk", "rows_written": len(rows)}

        parcels = collect_parcels()
        dtm_work = map_parcels_to_dtm_tiles(parcels)
        slope_work = map_parcels_to_slope_tiles(parcels)
        dtm_results = stats_for_dtm_tile.expand(work_item=dtm_work)
        slope_results = stats_for_slope_tile.expand(work_item=slope_work)
        rows = aggregate_per_parcel(dtm_results, slope_results)
        write_results(rows)

    return lidar_parcel_zonal_stats()


dag = _create_dag()
