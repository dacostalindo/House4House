"""
Idealista Bronze Loading — S03/S04

Loads Idealista property detail JSONL from MinIO into PostGIS bronze table.
One row per listing per scrape date in bronze_listings.raw_idealista.

Idempotent: DELETE WHERE _scrape_date = today's date before INSERT.
Trigger manually from Airflow UI after idealista_ingestion DAG completes.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field parsing helpers
# ---------------------------------------------------------------------------


def _parse_price(raw) -> float | None:
    """Parse price to float. Handles int, float, or string like '285 000'."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(" ", "").replace(",", ".").replace("\xa0", ""))
    except (ValueError, TypeError):
        return None


def _parse_area(raw) -> float | None:
    """Extract numeric value from area string like '95 m2' or '95.5'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"[\d]+[.,]?[\d]*", str(raw).replace(",", "."))
    return float(match.group().replace(",", ".")) if match else None


def _parse_int(raw) -> int | None:
    """Safe int parsing from any type."""
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def _parse_floor(raw) -> int | None:
    """Extract floor number from strings like '3rd floor', 'Ground floor', '3'."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).lower()
    if any(kw in s for kw in ("ground", "rés", "res-do-chao", "r/c")):
        return 0
    match = re.search(r"\d+", s)
    return int(match.group()) if match else None


def _parse_bool_feature(features: list, keywords: list[str]) -> bool:
    """True if any keyword is a case-insensitive substring of any feature string."""
    if not features:
        return False
    keywords_lower = [k.lower() for k in keywords]
    for feat in features:
        feat_lower = str(feat).lower()
        if any(kw in feat_lower for kw in keywords_lower):
            return True
    return False


def _parse_energy_class(raw) -> str | None:
    """Extract energy class letter from strings like 'A+', 'B', 'F', 'Isento'."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in ("exempt", "isento", "n/a", ""):
        return None
    match = re.match(r"^([A-Fa-f][+]?)$", s.strip())
    if match:
        return match.group(1).upper()
    return s[:2].upper() if len(s) >= 1 else None


def _parse_location_hierarchy(hierarchy) -> tuple[str | None, str | None, str | None]:
    """
    Extract (district, municipality, parish) from ZenRows location_hierarchy.
    Handles both list-of-objects with 'type' keys and positional arrays.
    """
    if not hierarchy:
        return None, None, None

    district = municipality = parish = None

    if isinstance(hierarchy, dict):
        # Direct dict: {"district": "Lisboa", "municipality": "Lisboa", ...}
        district = hierarchy.get("district") or hierarchy.get("distrito")
        municipality = (
            hierarchy.get("municipality")
            or hierarchy.get("concelho")
            or hierarchy.get("municipio")
        )
        parish = hierarchy.get("parish") or hierarchy.get("freguesia")
        return district, municipality, parish

    if isinstance(hierarchy, list):
        for idx, item in enumerate(hierarchy):
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).lower()
                name = item.get("name") or item.get("label")
                if "district" in item_type or "distrito" in item_type:
                    district = name
                elif any(
                    kw in item_type
                    for kw in ("municipality", "concelho", "municipio")
                ):
                    municipality = name
                elif "parish" in item_type or "freguesia" in item_type:
                    parish = name
            elif isinstance(item, str):
                # Positional: [district, municipality, parish]
                if idx == 0:
                    district = item
                elif idx == 1:
                    municipality = item
                elif idx == 2:
                    parish = item

    return district, municipality, parish


def _parse_date(raw) -> str | None:
    """Parse date from ISO string or Unix timestamp (ms). Returns YYYY-MM-DD or None."""
    if not raw:
        return None
    try:
        # ZenRows modified_at is Unix timestamp in milliseconds
        if isinstance(raw, (int, float)) and raw > 1_000_000_000:
            from datetime import datetime

            ts = raw / 1000 if raw > 1_000_000_000_000 else raw
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        return str(raw)[:10]
    except Exception:
        return None


def _parse_construction_year(features: list) -> int | None:
    """Extract construction year from property_features list."""
    for feat in features:
        match = re.search(r"(?:construído|built)\s+(?:em|in)\s+(\d{4})", str(feat).lower())
        if match:
            return int(match.group(1))
    return None


def _map_detail_to_row(detail: dict, scrape_date: str, batch_id: str) -> tuple:
    """
    Map a ZenRows property detail JSON object to a bronze INSERT row tuple.
    Column order must exactly match the INSERT SQL in load_listings.
    """
    features = detail.get("property_features") or []
    equipment = detail.get("property_equipment") or []
    all_feats = features + equipment

    district_raw, municipality_raw, parish_raw = _parse_location_hierarchy(
        detail.get("location_hierarchy")
    )

    operation = str(detail.get("operation", "")).lower() or detail.get("_operation")
    distrito = detail.get("_distrito", "")
    minio_path = (
        f"s3://raw/idealista/detail/{operation}/{distrito}/{scrape_date}.jsonl"
    )

    # ZenRows uses bedroom_count (singular) in detail, bedrooms_count in discovery
    bedrooms = detail.get("bedroom_count") or detail.get("bedrooms_count")

    images = detail.get("property_images") or []

    return (
        str(detail.get("_property_id") or detail.get("property_id", "")),
        detail.get("property_url"),
        operation,
        _parse_price(detail.get("property_price") or detail.get("price")),
        "EUR",
        detail.get("property_type"),
        detail.get("property_subtype"),
        str(bedrooms) if bedrooms is not None else None,
        _parse_area(detail.get("lot_size_usable") or detail.get("property_dimensions")),
        _parse_area(detail.get("lot_size") or detail.get("property_dimensions")),
        _parse_area(detail.get("lot_size")),
        _parse_int(bedrooms),
        _parse_int(detail.get("bathroom_count")),
        _parse_floor(detail.get("floor")),
        # Boolean features (all grouped together)
        _parse_bool_feature(all_feats, ["elevator", "lift", "elevador"]),
        _parse_bool_feature(all_feats, ["parking", "garagem", "estacionamento"]),
        _parse_bool_feature(all_feats, ["terrace", "terraco", "varanda"]),
        _parse_bool_feature(all_feats, ["garden", "jardim"]),
        _parse_bool_feature(all_feats, ["pool", "piscina", "swimming"]),
        _parse_bool_feature(all_feats, ["air conditioning", "ar condicionado", "climatização", "climatizacao"]),
        _parse_bool_feature(all_feats, ["heating", "aquecimento", "calefação", "calefacao"]),
        _parse_bool_feature(all_feats, ["balcony", "balcão", "balcao"]),
        _parse_bool_feature(all_feats, ["furnished kitchen", "cozinha equipada"]),
        _parse_bool_feature(all_feats, ["built-in wardrobes", "armários embutidos", "roupeiros", "armarios"]),
        _parse_bool_feature(features, ["exterior"]),
        # Property details
        _parse_energy_class(detail.get("energy_certificate")),
        _parse_construction_year(features),
        detail.get("property_condition"),
        detail.get("property_description"),
        detail.get("address"),
        district_raw,
        municipality_raw,
        parish_raw,
        detail.get("latitude"),
        detail.get("longitude"),
        _parse_date(detail.get("modified_at")),
        _parse_date(detail.get("modified_at")),
        # Agent info
        detail.get("agency_name"),
        None,  # agent_type — not in ZenRows
        detail.get("agency_phone"),
        # Metadata
        len(images) if images else None,
        _parse_date(detail.get("last_deactivated_at")),
        detail.get("status"),
        scrape_date,
        batch_id,
        minio_path,
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
                    id                   BIGSERIAL PRIMARY KEY,
                    source_listing_id    VARCHAR(50) NOT NULL,
                    listing_url          TEXT,
                    operation_type       VARCHAR(10),
                    price                NUMERIC(12,2),
                    currency             CHAR(3) DEFAULT 'EUR',
                    property_type_raw    VARCHAR(100),
                    property_subtype_raw VARCHAR(100),
                    typology_raw         VARCHAR(20),
                    useful_area_m2       NUMERIC(10,2),
                    gross_area_m2        NUMERIC(10,2),
                    plot_area_m2         NUMERIC(12,2),
                    num_rooms            SMALLINT,
                    num_bathrooms        SMALLINT,
                    floor_number         SMALLINT,
                    has_elevator         BOOLEAN,
                    has_parking          BOOLEAN,
                    has_terrace          BOOLEAN,
                    has_garden           BOOLEAN,
                    has_pool             BOOLEAN,
                    has_ac               BOOLEAN,
                    has_heating          BOOLEAN,
                    has_balcony          BOOLEAN,
                    has_furnished_kitchen BOOLEAN,
                    has_wardrobes        BOOLEAN,
                    is_exterior          BOOLEAN,
                    energy_class         CHAR(2),
                    construction_year    SMALLINT,
                    condition_raw        VARCHAR(50),
                    description_text     TEXT,
                    address_raw          TEXT,
                    district_raw         VARCHAR(100),
                    municipality_raw     VARCHAR(100),
                    parish_raw           VARCHAR(100),
                    latitude             NUMERIC(10,7),
                    longitude            NUMERIC(10,7),
                    listing_date         DATE,
                    update_date          DATE,
                    agent_name           VARCHAR(200),
                    agent_type           VARCHAR(50),
                    agent_phone          VARCHAR(50),
                    image_count          SMALLINT,
                    last_deactivated_at  DATE,
                    status_raw           VARCHAR(20),
                    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
                    _source              VARCHAR(30) DEFAULT 'idealista',
                    _scrape_date         DATE NOT NULL,
                    _batch_id            VARCHAR(50),
                    _raw_html_path       TEXT
                )
            """)

            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_idealista_source_id ON bronze_listings.raw_idealista(source_listing_id)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_scrape_date ON bronze_listings.raw_idealista(_scrape_date)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_operation ON bronze_listings.raw_idealista(operation_type, _scrape_date)",
                "CREATE INDEX IF NOT EXISTS idx_idealista_location ON bronze_listings.raw_idealista(district_raw, municipality_raw)",
            ]:
                cur.execute(idx_sql)

            log.info(
                "[idealista] Ensured bronze_listings.raw_idealista exists with indexes"
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
                    source_listing_id, listing_url, operation_type,
                    price, currency, property_type_raw, property_subtype_raw, typology_raw,
                    useful_area_m2, gross_area_m2, plot_area_m2,
                    num_rooms, num_bathrooms, floor_number,
                    has_elevator, has_parking, has_terrace, has_garden, has_pool,
                    has_ac, has_heating, has_balcony,
                    has_furnished_kitchen, has_wardrobes, is_exterior,
                    energy_class, construction_year, condition_raw,
                    description_text, address_raw,
                    district_raw, municipality_raw, parish_raw,
                    latitude, longitude,
                    listing_date, update_date,
                    agent_name, agent_type, agent_phone,
                    image_count, last_deactivated_at, status_raw,
                    _scrape_date, _batch_id, _raw_html_path
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
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
                SELECT operation_type, district_raw, COUNT(*)
                FROM bronze_listings.raw_idealista
                WHERE _scrape_date = %s
                GROUP BY operation_type, district_raw
                ORDER BY operation_type, district_raw
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

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_listings(files)
        table_ready >> loaded
        validate_counts(loaded)

    return idealista_bronze_load()


dag = _create_dag()
