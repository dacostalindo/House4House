"""SCE forward-geocoding DAG — Sprint-08 Activity 7 Phase 3.

Sits between `sce_bronze_load` and `dbt_sce_build` in the SCE pipeline
chain:

    sce_ingestion → sce_bronze_load → sce_geocode → dbt_sce_build
                                       (THIS DAG)

Reads SCE certificates not yet geocoded, runs a cascade against each:

    1. Nominatim forward-geocode of `geocode_query(morada, freguesia, concelho)`.
       Top hit → (lat, lon, importance, source='nominatim').
    2. Freguesia centroid from `gold_analytics.dim_geography` (DTMNFR
       reconstructed from query_distrito + query_concelho + query_freguesia).
       → (lat, lon, 0.2, source='freguesia_centroid').
    3. None → (NULL, NULL, 0.0, source='none').

Writes rows to `bronze_enrichment.raw_sce_geocoded` (created on first run).
Idempotent on `doc_number` — re-runs only geocode docs not already present.

v1 scope: Aveiro distrito (query_distrito = '1'). National rollout adds
the other distritos as the SCE scraper extends them.

See pipelines/enrichment/sce_address_norm.py (the address-norm + query
functions) and pipelines/common/geocoding.py (the Nominatim HTTP helper).
"""

from __future__ import annotations

import logging
from datetime import datetime

from airflow.decorators import dag, task

log = logging.getLogger(__name__)

# Aveiro distrito only for the v1 wedge. National rollout extends this.
V1_DISTRITO_CODE = "1"

# Confidence we assign to freguesia-centroid fallbacks. Low — surface to the
# UI as "fuzzy" so the Inspector can flag the address as approximate.
FREGUESIA_CENTROID_CONFIDENCE = 0.2


@dag(
    dag_id="sce_geocode",
    description=(
        "Forward-geocode SCE certificates via Nominatim (primary) + "
        "freguesia-centroid fallback. Incremental on doc_number. Triggers "
        "dbt_sce_build on success."
    ),
    schedule=None,  # manual / trigger-chained from sce_bronze_load
    start_date=datetime(2026, 5, 15),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data-engineering", "retries": 2, "retry_delay": 300},
    tags=["sce", "geocoding", "enrichment"],
)
def sce_geocode_dag():

    @task()
    def setup_schema_and_table() -> None:
        """Create bronze_enrichment schema + raw_sce_geocoded table on first run."""
        import psycopg2
        from airflow.models import Variable

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()
            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze_enrichment")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bronze_enrichment.raw_sce_geocoded (
                    doc_number          TEXT PRIMARY KEY,
                    address_lat         NUMERIC(10, 7),
                    address_lng         NUMERIC(10, 7),
                    geocode_source      TEXT NOT NULL,
                    geocode_confidence  NUMERIC(4, 3) NOT NULL,
                    normalized_address  TEXT,
                    nominatim_display   TEXT,
                    _geocoded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for idx_sql in (
                "CREATE INDEX IF NOT EXISTS idx_sce_geocoded_source "
                "ON bronze_enrichment.raw_sce_geocoded (geocode_source)",
                "CREATE INDEX IF NOT EXISTS idx_sce_geocoded_coords "
                "ON bronze_enrichment.raw_sce_geocoded (address_lat, address_lng) "
                "WHERE address_lat IS NOT NULL",
            ):
                cur.execute(idx_sql)
            conn.commit()
            log.info("[sce_geocode] schema + table ready")
        finally:
            conn.close()

    @task()
    def geocode_pending(_setup: None) -> dict:
        """Find SCE rows missing from raw_sce_geocoded and geocode them.

        For each pending row:
          1. Nominatim forward-geocode `geocode_query(...)`.
          2. Fallback: freguesia centroid from dim_geography (DTMNFR
             reconstructed via LPAD-2 on query_distrito/concelho/freguesia).
          3. Fallback: NULL coords + geocode_source='none'.

        Writes results in batches with ON CONFLICT (doc_number) DO NOTHING
        so re-runs are safe.
        """
        import psycopg2
        from airflow.models import Variable

        from pipelines.common.geocoding import nominatim_geocode_batch
        from pipelines.enrichment.sce_address_norm import (
            geocode_query,
            normalize_address,
        )

        nominatim_url = Variable.get("NOMINATIM_URL", "http://nominatim:8080")

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()

            # Pending = bronze SCE rows in Aveiro distrito not yet in geocoded
            cur.execute(
                """
                SELECT s.doc_number, s.morada, s.fracao, s.localidade,
                       s.freguesia_detail, s.concelho,
                       s.query_distrito, s.query_concelho, s.query_freguesia
                FROM bronze_regulatory.raw_sce_certificates s
                LEFT JOIN bronze_enrichment.raw_sce_geocoded g
                    ON g.doc_number = s.doc_number
                WHERE g.doc_number IS NULL
                  AND s.query_distrito = %s
                  AND s.morada IS NOT NULL
                """,
                (V1_DISTRITO_CODE,),
            )
            pending = cur.fetchall()
            log.info("[sce_geocode] %d pending SCE rows to geocode", len(pending))

            if not pending:
                return {"pending": 0, "nominatim_hits": 0,
                        "freguesia_fallbacks": 0, "no_hits": 0}

            # Build (doc_number, query) pairs + a lookup for fallback inputs
            queries = []
            row_by_doc: dict[str, dict] = {}
            for doc, morada, fracao, localidade, freguesia, concelho, qd, qc, qf in pending:
                queries.append((doc, geocode_query(morada, freguesia, concelho)))
                row_by_doc[doc] = {
                    "morada": morada, "fracao": fracao, "localidade": localidade,
                    "freguesia_detail": freguesia, "concelho": concelho,
                    "query_distrito": qd, "query_concelho": qc, "query_freguesia": qf,
                }

            # Nominatim primary pass
            insert_sql = """
                INSERT INTO bronze_enrichment.raw_sce_geocoded (
                    doc_number, address_lat, address_lng,
                    geocode_source, geocode_confidence,
                    normalized_address, nominatim_display
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_number) DO NOTHING
            """

            nominatim_hits = 0
            need_fallback: list[str] = []
            for doc, result in nominatim_geocode_batch(queries, url=nominatim_url):
                row = row_by_doc[doc]
                norm_addr = normalize_address(
                    row["morada"], row["fracao"], row["localidade"], row["concelho"],
                )

                if result is not None:
                    cur.execute(insert_sql, (
                        doc, result.lat, result.lon,
                        "nominatim", result.importance,
                        norm_addr, result.display_name,
                    ))
                    nominatim_hits += 1
                else:
                    need_fallback.append(doc)

                if (nominatim_hits + len(need_fallback)) % 200 == 0:
                    conn.commit()
            conn.commit()

            # Freguesia-centroid fallback for unresolved rows
            freguesia_fallbacks = 0
            no_hits = 0
            for doc in need_fallback:
                row = row_by_doc[doc]
                dtmnfr = (
                    f"{int(row['query_distrito']):02d}"
                    f"{int(row['query_concelho']):02d}"
                    f"{int(row['query_freguesia']):02d}"
                ) if all(row[k] for k in ("query_distrito", "query_concelho", "query_freguesia")) else None

                norm_addr = normalize_address(
                    row["morada"], row["fracao"], row["localidade"], row["concelho"],
                )

                if dtmnfr:
                    cur.execute(
                        "SELECT ST_Y(centroid), ST_X(centroid) "
                        "FROM gold_analytics.dim_geography WHERE freguesia_code = %s",
                        (dtmnfr,),
                    )
                    hit = cur.fetchone()
                else:
                    hit = None

                if hit and hit[0] is not None:
                    cur.execute(insert_sql, (
                        doc, hit[0], hit[1],
                        "freguesia_centroid", FREGUESIA_CENTROID_CONFIDENCE,
                        norm_addr, None,
                    ))
                    freguesia_fallbacks += 1
                else:
                    cur.execute(insert_sql, (
                        doc, None, None,
                        "none", 0.0,
                        norm_addr, None,
                    ))
                    no_hits += 1

            conn.commit()
            cur.close()

        finally:
            conn.close()

        stats = {
            "pending": len(pending),
            "nominatim_hits": nominatim_hits,
            "freguesia_fallbacks": freguesia_fallbacks,
            "no_hits": no_hits,
        }
        log.info("[sce_geocode] done: %s", stats)
        return stats

    @task()
    def report_coverage(stats: dict) -> dict:
        """Compute overall coverage stats post-run. Surfaces the >= 90 % gate."""
        import psycopg2
        from airflow.models import Variable

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE address_lat IS NOT NULL) AS with_coords,
                       COUNT(*) FILTER (WHERE geocode_source = 'nominatim') AS nominatim,
                       COUNT(*) FILTER (WHERE geocode_source = 'freguesia_centroid') AS freguesia
                FROM bronze_enrichment.raw_sce_geocoded
                """
            )
            total, with_coords, nominatim, freguesia = cur.fetchone()
        finally:
            conn.close()

        coverage = {
            "this_run": stats,
            "lifetime": {
                "total_geocoded_rows": total,
                "with_coords": with_coords,
                "pct_with_coords": round(100.0 * with_coords / max(total, 1), 2),
                "nominatim": nominatim,
                "freguesia_centroid": freguesia,
            },
        }
        log.info("[sce_geocode] coverage: %s", coverage)
        return coverage

    # ── trigger dbt rebuild only after geocoding done ──
    from airflow.operators.trigger_dagrun import TriggerDagRunOperator
    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_sce_build",
        trigger_dag_id="dbt_sce_build",
        wait_for_completion=False,
        reset_dag_run=True,
    )

    setup = setup_schema_and_table()
    run_stats = geocode_pending(setup)
    coverage = report_coverage(run_stats)
    coverage >> trigger_dbt


dag = sce_geocode_dag()
