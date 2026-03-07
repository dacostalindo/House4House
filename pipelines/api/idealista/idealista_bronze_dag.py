"""
Idealista Bronze Loading — S03/S04

Loads Idealista property detail JSONL from MinIO into PostGIS bronze table.
One row per listing per scrape date in bronze_listings.raw_idealista.

Source-oriented: stores raw ZenRows fields as-is (TEXT, JSONB, BIGINT).
All parsing and transformation belongs in the silver/dbt layer.

Idempotent: DELETE WHERE _scrape_date = today's date before INSERT.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)


def _map_detail_to_row(detail: dict, scrape_date: str, batch_id: str) -> tuple:
    """
    Thin passthrough from ZenRows JSON to bronze INSERT tuple.
    Only safe coercions: arrays → JSONB via json.dumps, lat/long left as-is.
    """
    operation = detail.get("_operation", "") or str(detail.get("operation", "")).lower()
    distrito = detail.get("_distrito", "")
    minio_path = f"s3://raw/idealista/detail/{operation}/{distrito}/{scrape_date.replace('-', '')}.jsonl"

    def _jsonb(val):
        if val is None:
            return None
        return json.dumps(val, ensure_ascii=False)

    def _text(val):
        if val is None:
            return None
        return str(val)

    return (
        scrape_date,
        batch_id,
        minio_path,
        bool(detail.get("_carried_forward", False)),
        # Internal keys
        _text(detail.get("_property_id") or detail.get("property_id")),
        distrito,
        operation,
        # Property identifiers
        _text(detail.get("property_id")),
        detail.get("property_url"),
        detail.get("property_type"),
        detail.get("property_subtype"),
        # Price — raw TEXT
        _text(detail.get("property_price")),
        detail.get("price_currency_symbol"),
        # Areas — raw TEXT
        _text(detail.get("lot_size")),
        _text(detail.get("lot_size_usable")),
        _text(detail.get("property_dimensions")),
        # Rooms — raw TEXT
        _text(detail.get("bedroom_count")),
        _text(detail.get("bedrooms_count")),
        _text(detail.get("bathroom_count")),
        # Floor — raw TEXT
        _text(detail.get("floor")),
        detail.get("floor_description"),
        # Features / equipment — JSONB arrays
        _jsonb(detail.get("property_features")),
        _jsonb(detail.get("property_equipment")),
        # Images — JSONB arrays
        _jsonb(detail.get("property_images")),
        _jsonb(detail.get("property_image_tags")),
        # Property details — raw TEXT
        detail.get("property_condition"),
        detail.get("property_description"),
        detail.get("property_title"),
        _text(detail.get("energy_certificate")),
        detail.get("address"),
        detail.get("location_name"),
        # Location — JSONB (polymorphic: dict or list)
        _jsonb(detail.get("location_hierarchy")),
        detail.get("latitude"),
        detail.get("longitude"),
        detail.get("country"),
        # Agency
        detail.get("agency_name"),
        detail.get("agency_phone"),
        detail.get("agency_logo"),
        # Timestamps / status — raw
        detail.get("modified_at"),
        detail.get("status"),
        _text(detail.get("last_deactivated_at")),
        detail.get("operation"),
    )


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="idealista_bronze_load",
        description="Load Idealista property detail JSONL from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["idealista", "bronze", "listings", "postgis"],
    )
    def idealista_bronze_load():

        @task()
        def list_minio_files() -> list[dict]:
            """Find today's detail JSONL files in MinIO."""
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.idealista.idealista_config import (
                MINIO_BUCKET,
                MINIO_PREFIX,
            )

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            scrape_date = date.today().strftime("%Y%m%d")
            files = []

            objects = list(
                client.list_objects(
                    MINIO_BUCKET,
                    prefix=f"{MINIO_PREFIX}/detail/",
                    recursive=True,
                )
            )
            for obj in objects:
                if scrape_date in obj.object_name and obj.object_name.endswith(
                    ".jsonl"
                ):
                    parts = obj.object_name.split("/")
                    # path: idealista/detail/{operation}/{distrito}/{YYYYMMDD}.jsonl
                    if len(parts) >= 5:
                        files.append(
                            {
                                "minio_path": obj.object_name,
                                "operation": parts[2],
                                "distrito": parts[3],
                            }
                        )

            log.info(
                "[idealista] Found %d detail files for scrape date %s",
                len(files),
                scrape_date,
            )
            return files

        @task()
        def create_table() -> None:
            """Create bronze_listings.raw_idealista if it doesn't exist."""
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bronze_listings.raw_idealista (
                    id                    BIGSERIAL PRIMARY KEY,

                    -- Metadata
                    _scrape_date          DATE NOT NULL,
                    _batch_id             VARCHAR(50),
                    _minio_path           TEXT,
                    _ingested_at          TIMESTAMPTZ DEFAULT NOW(),
                    _source               VARCHAR(30) DEFAULT 'idealista',
                    _carried_forward      BOOLEAN DEFAULT FALSE,

                    -- Internal keys
                    _property_id          TEXT,
                    _distrito             TEXT,
                    _operation            TEXT,

                    -- Property identifiers
                    property_id           TEXT,
                    property_url          TEXT,
                    property_type         TEXT,
                    property_subtype      TEXT,

                    -- Price (raw)
                    property_price        TEXT,
                    price_currency_symbol TEXT,

                    -- Areas (raw)
                    lot_size              TEXT,
                    lot_size_usable       TEXT,
                    property_dimensions   TEXT,

                    -- Rooms (raw)
                    bedroom_count         TEXT,
                    bedrooms_count        TEXT,
                    bathroom_count        TEXT,

                    -- Floor (raw)
                    floor                 TEXT,
                    floor_description     TEXT,

                    -- Features / equipment (JSONB arrays)
                    property_features     JSONB,
                    property_equipment    JSONB,

                    -- Images (JSONB arrays)
                    property_images       JSONB,
                    property_image_tags   JSONB,

                    -- Property details (raw)
                    property_condition    TEXT,
                    property_description  TEXT,
                    property_title        TEXT,
                    energy_certificate    TEXT,
                    address               TEXT,
                    location_name         TEXT,

                    -- Location
                    location_hierarchy    JSONB,
                    latitude              NUMERIC(10,7),
                    longitude             NUMERIC(10,7),
                    country               TEXT,

                    -- Agency
                    agency_name           TEXT,
                    agency_phone          TEXT,
                    agency_logo           TEXT,

                    -- Timestamps / status (raw)
                    modified_at           BIGINT,
                    status                TEXT,
                    last_deactivated_at   TEXT,
                    operation             TEXT
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_idealista_property_id ON bronze_listings.raw_idealista(_property_id)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_scrape_date ON bronze_listings.raw_idealista(_scrape_date)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_operation ON bronze_listings.raw_idealista(_operation, _scrape_date)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_distrito ON bronze_listings.raw_idealista(_distrito)",
            ]:
                cur.execute(idx_sql)

            # Reverse geocoded lookup table (Nominatim)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bronze_listings.reverse_geocoded (
                    latitude       NUMERIC(10,7)  NOT NULL,
                    longitude      NUMERIC(10,7)  NOT NULL,
                    display_name   TEXT,
                    road           TEXT,
                    house_number   TEXT,
                    postcode       TEXT,
                    city_district  TEXT,
                    city           TEXT,
                    raw_response   JSONB,
                    _geocoded_at   TIMESTAMPTZ    DEFAULT NOW(),
                    PRIMARY KEY (latitude, longitude)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_reverse_geocoded_postcode
                    ON bronze_listings.reverse_geocoded (postcode)
            """)

            log.info(
                "[idealista] Ensured bronze_listings.raw_idealista "
                "and reverse_geocoded exist with indexes"
            )
            cur.close()
            conn.close()

        @task()
        def load_listings(minio_files: list[dict]) -> dict:
            """
            Parse each detail JSONL file and load into bronze_listings.raw_idealista.
            Idempotent: DELETE today's rows before INSERT.
            """
            import psycopg2
            import psycopg2.extras
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.idealista.idealista_config import MINIO_BUCKET

            minio_client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            scrape_date = date.today().strftime("%Y-%m-%d")
            batch_id = date.today().strftime("%Y%m%dT%H%M%S")

            # Idempotent delete of today's data
            cur.execute(
                "DELETE FROM bronze_listings.raw_idealista WHERE _scrape_date = %s",
                (scrape_date,),
            )
            conn.commit()
            log.info(
                "[idealista] Deleted existing rows for _scrape_date=%s", scrape_date
            )

            insert_sql = """
                INSERT INTO bronze_listings.raw_idealista (
                    _scrape_date, _batch_id, _minio_path, _carried_forward,
                    _property_id, _distrito, _operation,
                    property_id, property_url, property_type, property_subtype,
                    property_price, price_currency_symbol,
                    lot_size, lot_size_usable, property_dimensions,
                    bedroom_count, bedrooms_count, bathroom_count,
                    floor, floor_description,
                    property_features, property_equipment,
                    property_images, property_image_tags,
                    property_condition, property_description, property_title,
                    energy_certificate, address, location_name,
                    location_hierarchy, latitude, longitude, country,
                    agency_name, agency_phone, agency_logo,
                    modified_at, status, last_deactivated_at, operation
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
            """

            total_rows = 0
            results = {}

            for file_info in minio_files:
                minio_path = file_info["minio_path"]
                operation = file_info["operation"]
                distrito = file_info["distrito"]
                segment_key = f"{operation}/{distrito}"

                resp = minio_client.get_object(MINIO_BUCKET, minio_path)
                raw_bytes = resp.read()
                resp.close()
                resp.release_conn()

                rows = []
                for line in raw_bytes.decode("utf-8").split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    detail = json.loads(line)
                    rows.append(_map_detail_to_row(detail, scrape_date, batch_id))

                if not rows:
                    log.warning("[idealista] %s: no rows parsed", segment_key)
                    results[segment_key] = 0
                    continue

                # Batch insert
                for start in range(0, len(rows), 1000):
                    batch = rows[start : start + 1000]
                    psycopg2.extras.execute_batch(
                        cur, insert_sql, batch, page_size=500
                    )

                conn.commit()
                total_rows += len(rows)
                results[segment_key] = len(rows)
                log.info("[idealista] %s: loaded %d rows", segment_key, len(rows))

            cur.close()
            conn.close()
            log.info("[idealista] Total: %d rows loaded", total_rows)
            return results

        @task()
        def validate_counts(load_results: dict) -> dict:
            """Verify total row count for today's scrape date."""
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

            scrape_date = date.today().strftime("%Y-%m-%d")
            cur.execute(
                "SELECT COUNT(*) FROM bronze_listings.raw_idealista WHERE _scrape_date = %s",
                (scrape_date,),
            )
            count = cur.fetchone()[0]

            cur.execute(
                """
                SELECT _operation, _distrito, COUNT(*)
                FROM bronze_listings.raw_idealista
                WHERE _scrape_date = %s
                GROUP BY _operation, _distrito
                ORDER BY _operation, _distrito
            """,
                (scrape_date,),
            )
            breakdown = cur.fetchall()

            cur.close()
            conn.close()

            log.info("[idealista] Total rows for %s: %d", scrape_date, count)
            for op, dist, cnt in breakdown:
                log.info("[idealista]   %s / %s: %d rows", op, dist, cnt)

            total_from_load = sum(load_results.values())
            if count < total_from_load:
                raise ValueError(
                    f"bronze_listings.raw_idealista: DB count ({count}) "
                    f"< loaded ({total_from_load})"
                )
            return {
                "scrape_date": scrape_date,
                "total_rows": count,
                "breakdown": {
                    f"{op}/{dist}": cnt for op, dist, cnt in breakdown
                },
            }

        @task()
        def reverse_geocode(validate_result: dict) -> dict:
            """
            Incrementally reverse-geocode listing coordinates via local Nominatim.
            Only calls Nominatim for (lat, lon) pairs not already in the lookup table.
            """
            import psycopg2
            import time

            import requests
            from airflow.models import Variable

            NOMINATIM_URL = Variable.get("NOMINATIM_URL", "http://nominatim:8080")
            RATE_LIMIT_SECONDS = 0.02  # ~50 req/s for local Nominatim

            conn = psycopg2.connect(
                host=Variable.get("WAREHOUSE_HOST"),
                port=int(Variable.get("WAREHOUSE_PORT")),
                dbname=Variable.get("WAREHOUSE_DB"),
                user=Variable.get("WAREHOUSE_USER"),
                password=Variable.get("WAREHOUSE_PASSWORD"),
            )
            cur = conn.cursor()

            # Find coordinates not yet geocoded
            cur.execute("""
                SELECT DISTINCT r.latitude, r.longitude
                FROM bronze_listings.raw_idealista r
                LEFT JOIN bronze_listings.reverse_geocoded g
                    ON r.latitude = g.latitude AND r.longitude = g.longitude
                WHERE r.latitude IS NOT NULL
                  AND r.longitude IS NOT NULL
                  AND g.latitude IS NULL
            """)
            missing = cur.fetchall()
            log.info("[geocode] %d new coordinate pairs to geocode", len(missing))

            insert_sql = """
                INSERT INTO bronze_listings.reverse_geocoded
                    (latitude, longitude, display_name, road, house_number,
                     postcode, city_district, city, raw_response)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (latitude, longitude) DO NOTHING
            """

            geocoded = 0
            errors = 0

            for lat, lon in missing:
                try:
                    resp = requests.get(
                        f"{NOMINATIM_URL}/reverse",
                        params={
                            "lat": float(lat),
                            "lon": float(lon),
                            "format": "jsonv2",
                            "addressdetails": 1,
                        },
                        timeout=10,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    addr = data.get("address", {})
                    road = addr.get("road") or addr.get("square")
                    city = (
                        addr.get("city")
                        or addr.get("town")
                        or addr.get("village")
                    )

                    cur.execute(insert_sql, (
                        lat,
                        lon,
                        data.get("display_name"),
                        road,
                        addr.get("house_number"),
                        addr.get("postcode"),
                        addr.get("city_district"),
                        city,
                        json.dumps(data, ensure_ascii=False),
                    ))
                    geocoded += 1

                    if geocoded % 100 == 0:
                        conn.commit()
                        log.info(
                            "[geocode] Progress: %d / %d geocoded",
                            geocoded,
                            len(missing),
                        )

                except Exception as exc:
                    log.warning(
                        "[geocode] Failed for (%s, %s): %s", lat, lon, exc
                    )
                    errors += 1

                time.sleep(RATE_LIMIT_SECONDS)

            conn.commit()
            cur.close()
            conn.close()

            log.info(
                "[geocode] Done: %d geocoded, %d errors out of %d total",
                geocoded,
                errors,
                len(missing),
            )
            return {
                "new_geocoded": geocoded,
                "errors": errors,
                "total_missing_before": len(missing),
            }

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_listings(files)
        table_ready >> loaded
        validated = validate_counts(loaded)
        geocoded = reverse_geocode(validated)

        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_scoped_build",
            conf={"select": "stg_idealista+"},
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        geocoded >> trigger_dbt

    return idealista_bronze_load()


dag = _create_dag()
