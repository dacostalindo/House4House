"""
INE Bronze Loading — S01/S29

Loads INE API indicator JSON files from MinIO into PostGIS bronze table.
33 indicators flattened into a single table: bronze_ine.raw_indicators.
One row per (indicator × period × geography × dimensions) tuple.

Trigger manually from Airflow UI — no schedule.
No config parameters needed — loads the latest JSON per indicator from MinIO.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# All 33 indicator codes — kept in sync with ine_config.py
INDICATOR_CODES = [
    # Housing: prices
    "0009201", "0009207", "0012234", "0012235",
    # Housing: transactions
    "0012785", "0012786", "0012787", "0012788",
    # Housing: rental market
    "0012571", "0012572", "0012573", "0012574",
    # Housing: construction
    "0012096", "0012778", "0011750",
    # Housing: mortgage finance
    "0006340", "0006341", "0008867", "0008870",
    # Housing: sales (updated methodology)
    "0012236",
    # Housing: construction (additional)
    "0012097", "0008321",
    # Housing: building stock (Census 2021)
    "0012575", "0012581",
    # Demographics
    "0001271", "0008273", "0008337",
    # Tourism
    "0009808",
    # Economy
    "0008351", "0011190",
    # Innovation
    "0008515", "0008519", "0008521",
]


def _parse_valor(raw: str | None) -> float | None:
    """Parse INE valor string to numeric. Returns None for convention codes."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw in ("x", "X", "..", "…", "||", "-"):
        return None
    try:
        return float(raw.replace(",", ".").replace("\xa0", ""))
    except (ValueError, TypeError):
        return None


def _parse_date(date_str: str | None) -> str | None:
    """Parse date string like '2025-06-18' to date. Returns None on failure."""
    if not date_str:
        return None
    try:
        return date_str[:10]
    except Exception:
        return None


def _parse_timestamp(ts_str: str | None) -> str | None:
    """Parse ISO timestamp like '2026-03-02T21:11:36.276Z'. Returns None on failure."""
    if not ts_str:
        return None
    try:
        return ts_str.replace("Z", "+00:00")
    except Exception:
        return None


def _flatten_indicator(raw_json: dict, batch_id: str) -> list[tuple]:
    """Flatten a single INE indicator JSON into rows for INSERT."""
    indicator_code = raw_json.get("IndicadorCod", "")
    indicator_name = raw_json.get("IndicadorDsg")
    last_updated = _parse_date(raw_json.get("DataUltimoAtualizacao"))
    extraction_ts = _parse_timestamp(raw_json.get("DataExtracao"))

    dados = raw_json.get("Dados", {})
    if not isinstance(dados, dict):
        return []

    rows = []
    for period, observations in dados.items():
        if not isinstance(observations, list):
            continue
        for obs in observations:
            rows.append((
                indicator_code,
                indicator_name,
                last_updated,
                period,
                obs.get("geocod"),
                obs.get("geodsg"),
                obs.get("dim_3"),
                obs.get("dim_3_t"),
                obs.get("dim_4"),
                obs.get("dim_4_t"),
                obs.get("dim_5"),
                obs.get("dim_5_t"),
                _parse_valor(obs.get("valor")),
                obs.get("ind_string"),
                obs.get("sinal_conv"),
                obs.get("sinal_conv_desc"),
                batch_id,
                extraction_ts,
            ))
    return rows


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
        dag_id="ine_bronze_load",
        description="Load INE API indicator JSON from MinIO into PostGIS bronze table",
        schedule=None,
        start_date=None,
        catchup=False,
        default_args=default_args,
        tags=["ine", "bronze", "indicators", "postgis"],
    )
    def ine_bronze_load():

        @task()
        def list_minio_files() -> dict:
            """Find the latest JSON file per indicator code in MinIO."""
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            latest_files = {}
            for code in INDICATOR_CODES:
                objects = list(client.list_objects("raw", prefix=f"ine/{code}/", recursive=True))
                json_objects = [o for o in objects if o.object_name.endswith(".json")]
                if json_objects:
                    latest = sorted(json_objects, key=lambda o: o.object_name)[-1]
                    latest_files[code] = latest.object_name
                    log.info("[ine] %s → %s (%.1f KB)", code, latest.object_name, latest.size / 1024)
                else:
                    log.warning("[ine] No JSON found for indicator %s", code)

            log.info("[ine] Found %d / %d indicator files", len(latest_files), len(INDICATOR_CODES))
            return latest_files

        @task()
        def create_table() -> None:
            """Create bronze_ine.raw_indicators if it doesn't exist."""
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
                CREATE TABLE IF NOT EXISTS bronze_ine.raw_indicators (
                    id                   BIGSERIAL PRIMARY KEY,
                    indicator_code       VARCHAR(20) NOT NULL,
                    indicator_name       TEXT,
                    last_updated         DATE,
                    time_period          VARCHAR(50) NOT NULL,
                    geocod               VARCHAR(20),
                    geodsg               VARCHAR(200),
                    dim_3                VARCHAR(20),
                    dim_3_t              VARCHAR(200),
                    dim_4                VARCHAR(20),
                    dim_4_t              VARCHAR(200),
                    dim_5                VARCHAR(20),
                    dim_5_t              VARCHAR(200),
                    valor                NUMERIC(15,4),
                    ind_string           VARCHAR(50),
                    sinal_conv           VARCHAR(10),
                    sinal_conv_desc      VARCHAR(100),
                    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
                    _source              VARCHAR(50) DEFAULT 'ine_api',
                    _batch_id            VARCHAR(50),
                    _api_extraction_ts   TIMESTAMPTZ
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ine_ind_code
                ON bronze_ine.raw_indicators(indicator_code)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ine_ind_period
                ON bronze_ine.raw_indicators(indicator_code, time_period)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_ine_ind_geo
                ON bronze_ine.raw_indicators(indicator_code, geocod)
            """)
            log.info("[ine] Ensured bronze_ine.raw_indicators exists with indexes")

            cur.close()
            conn.close()

        @task()
        def load_indicators(latest_files: dict) -> dict:
            """Parse JSON files and load into bronze_ine.raw_indicators."""
            import psycopg2
            import psycopg2.extras
            from minio import Minio
            from airflow.models import Variable

            client = Minio(
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

            batch_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            insert_sql = """
                INSERT INTO bronze_ine.raw_indicators (
                    indicator_code, indicator_name, last_updated,
                    time_period, geocod, geodsg,
                    dim_3, dim_3_t, dim_4, dim_4_t, dim_5, dim_5_t,
                    valor, ind_string, sinal_conv, sinal_conv_desc,
                    _batch_id, _api_extraction_ts
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
            """

            results = {}
            total_rows = 0

            for code, object_name in latest_files.items():
                # Read JSON from MinIO
                resp = client.get_object("raw", object_name)
                raw_data = json.loads(resp.read())
                resp.close()
                resp.release_conn()

                # Navigate INE response structure
                if isinstance(raw_data, list) and len(raw_data) > 0:
                    root = raw_data[0]
                else:
                    root = raw_data

                # Delete existing rows for this indicator (full-refresh per indicator)
                cur.execute(
                    "DELETE FROM bronze_ine.raw_indicators WHERE indicator_code = %s",
                    (code,),
                )

                indicator_batch_id = f"{code}_{batch_id}"
                rows = _flatten_indicator(root, indicator_batch_id)

                if not rows:
                    log.warning("[ine] %s: no observations to load", code)
                    results[code] = 0
                    continue

                # Batch insert
                batch_size = 10_000
                for start in range(0, len(rows), batch_size):
                    batch = rows[start:start + batch_size]
                    psycopg2.extras.execute_batch(cur, insert_sql, batch, page_size=1000)

                conn.commit()
                total_rows += len(rows)
                results[code] = len(rows)
                log.info("[ine] %s: loaded %d rows", code, len(rows))

            cur.close()
            conn.close()

            log.info("[ine] Total: %d rows across %d indicators", total_rows, len(results))
            return results

        @task()
        def validate_counts(load_results: dict) -> dict:
            """Verify every indicator has rows in the table."""
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

            cur.execute("""
                SELECT indicator_code, COUNT(*)
                FROM bronze_ine.raw_indicators
                GROUP BY indicator_code
                ORDER BY indicator_code
            """)
            db_counts = dict(cur.fetchall())

            cur.execute("SELECT COUNT(*) FROM bronze_ine.raw_indicators")
            total = cur.fetchone()[0]

            cur.close()
            conn.close()

            missing = []
            for code in INDICATOR_CODES:
                count = db_counts.get(code, 0)
                if count == 0:
                    missing.append(code)
                    log.warning("[ine] %s: 0 rows in database", code)
                else:
                    log.info("[ine] %s: %d rows", code, count)

            if missing:
                log.warning("[ine] %d indicators with 0 rows: %s", len(missing), missing)

            log.info("[ine] Total rows in bronze_ine.raw_indicators: %d", total)
            log.info("[ine] Indicators loaded: %d / %d", len(db_counts), len(INDICATOR_CODES))

            return {"total_rows": total, "indicators_loaded": len(db_counts), "missing": missing}

        # --- Task wiring ---
        files = list_minio_files()
        table_ready = create_table()
        loaded = load_indicators(files)
        table_ready >> loaded
        validate_counts(loaded)

    return ine_bronze_load()


dag = _create_dag()
