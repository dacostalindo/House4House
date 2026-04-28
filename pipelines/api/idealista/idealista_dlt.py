"""Idealista PT developments + units — dlt-driven SCD2 bronze ingestion DAG.

Distinct from `idealista_ingestion` (the resale-listings pipeline using the
ZenRows Real Estate API discovery+detail). This DAG covers
`/comprar-empreendimentos/` — new-construction developments and their member
units. Pass 1+2 use the ZenRows Universal Scraper (only path to discover
developments and their child unit IDs); Pass 3 uses the ZenRows Real Estate
API with `tld=.pt` (5× cheaper than Universal, structured JSON, no parsing).

The two pipelines coexist. The resale `raw_idealista` table is slated for
eventual decommissioning; this pipeline keeps RE API field names verbatim
in the `idealista_development_units` table to enable a drop-in replacement
when that decommission happens.

Tasks (in order):

  audit_to_minio   — best-effort raw-HTML mirror of Pass 1 discovery pages
                     for replay. Pass 2 (dev) HTML and Pass 3 (RE API JSON)
                     are NOT mirrored — too granular at AML+distritos scope.

  load_facts       — runs idealista_developments_facts_source via dlt:
                     developments + development_units SCD2 + their two
                     heartbeat sidecars. Pass 2 + Pass 3 enrichment is
                     pre-fetched in parallel inside source._ensure_payload().
                     Hard-fails the DAG on schema-contract violation.
                     Returns counters via XCom for the validator.

  validate_facts   — asserts the load landed: _dlt_loads row status=0,
                     dev/unit row counts in expected bands, Pass 2 enrichment
                     ≥80%, Pass 3 enrichment (units_current / pass2_unit_links)
                     ≥95%, Pass 3 stub rate <10%, Pass 3 RE API error rate <5%.

Schedule: 0 6 * * 3 (Wednesdays 06:00 UTC). Wednesday slot avoids the Monday
(zome) and Tuesday (remax) clashes and keeps a free workday for re-runs.

Cost (estimate; refine after first Aveiro run):
  Pass 1 (Universal):  ~30 calls × $0.007 = $0.21
  Pass 2 (Universal):  ~700 calls × $0.007 = $4.90
  Pass 3 (RE API):     ~14-21k calls × $0.0015 = $21-32
  Total per run:       ~$26-38   (~$110-160/month at weekly cadence)

Aveiro test override: trigger with config
  {"target_areas_override": {"aveiro": ["aveiro-distrito"]}}
to scope the run to a single distrito for verification before full scope.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import dlt
from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable
from airflow.models.param import Param

from pipelines.api.idealista.source import (
    TARGET_AREAS,
    _build_discovery_url,
    _zenrows_get,
    get_pass3_counters,
    get_plots_pass2_counters,
    idealista_developments_facts_source,
    idealista_plots_facts_source,
)


log = logging.getLogger(__name__)

PIPELINES_DIR = "/opt/airflow/dlt_state/idealista_developments"
PIPELINES_DIR_PLOTS = "/opt/airflow/dlt_state/idealista_plots"
DATASET_NAME = "bronze_listings"
MINIO_BUCKET = "raw"
MINIO_PREFIX = "idealista_developments"

# Validation thresholds — see docstring.
PASS2_ENRICHMENT_FLOOR = 0.80
PASS3_ENRICHMENT_FLOOR = 0.95
PASS3_STUB_RATE_CEILING = 0.10
PASS3_ERROR_RATE_CEILING = 0.05


def _postgres_credentials() -> dict:
    return {
        "host": os.environ["WAREHOUSE_HOST"],
        "port": int(os.environ.get("WAREHOUSE_PORT", "5432")),
        "username": os.environ["WAREHOUSE_USER"],
        "password": os.environ["WAREHOUSE_PASSWORD"],
        "database": os.environ["WAREHOUSE_DB"],
    }


def _alert_on_failure(context: dict) -> None:
    """task_failure_callback — surfaces schema-freeze / SCD2 / scrape failures."""
    task_id = context.get("task_instance").task_id
    dag_id = context.get("task_instance").dag_id
    run_id = context.get("run_id")
    exception = context.get("exception")
    log.error(
        "[ALERT] %s.%s failed (run %s): %s",
        dag_id, task_id, run_id, exception,
    )


def _set_zenrows_env() -> None:
    """Push the ZenRows API key from Airflow Variable into env so source.py picks it up."""
    os.environ["ZENROWS_API_KEY"] = Variable.get("ZENROWS_API_KEY")


default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": _alert_on_failure,
}


with DAG(
    dag_id="idealista_developments_dlt",  # stable across the file rename — preserves Airflow history
    description=(
        "Idealista PT new-construction developments + units bronze ingestion via dlt. "
        "SCD2 for both, UPSERT sidecar heartbeats. Pass 1+2 Universal Scraper, "
        "Pass 3 RE API (tld=.pt)."
    ),
    schedule="0 6 * * 3",
    start_date=datetime(2026, 1, 1),  # static past date; manual triggers must satisfy this
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    params={
        "target_areas_override": Param(
            default=None,
            description=(
                "Optional dict overriding source.TARGET_AREAS for this run only. "
                "Example: {\"aveiro\": [\"aveiro-distrito\"]} to scope to one distrito. "
                "Auditable in Airflow run config; no code edit to revert."
            ),
            type=["null", "object"],
        ),
    },
    tags=["idealista", "bronze", "dlt", "scd2", "zenrows"],
) as dag:

    @task()
    def audit_to_minio(**context) -> dict:
        """Best-effort raw-HTML mirror of Pass 1 discovery pages.

        One HTML file per area per discovery page (page 1 only, as a "site
        shape did not change" check). Pass 2 / Pass 3 payloads are not
        mirrored — too granular. Honors the target_areas_override Param so
        an Aveiro test run mirrors only Aveiro.
        """
        from minio import Minio

        _set_zenrows_env()
        override = (context.get("params") or {}).get("target_areas_override")
        areas = override if override else TARGET_AREAS

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        endpoint = Variable.get("MINIO_ENDPOINT", default_var="minio:9000")
        client = Minio(
            endpoint,
            access_key=Variable.get("MINIO_ACCESS_KEY"),
            secret_key=Variable.get("MINIO_SECRET_KEY"),
            secure=False,
        )
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)

        uploaded: list[str] = []
        for area_key, slugs in areas.items():
            for slug in slugs:
                url = _build_discovery_url(slug, 1)
                html = _zenrows_get(url, wait_for="article.item")
                if html is None:
                    log.warning("[idealista_dev_dlt] audit: no HTML for %s", url)
                    continue
                with TemporaryDirectory() as td:
                    fp = Path(td) / "page1.html"
                    fp.write_text(html, encoding="utf-8")
                    obj = f"{MINIO_PREFIX}/discovery/{area_key}/{slug}/{ts}.html"
                    client.fput_object(MINIO_BUCKET, obj, str(fp))
                    uploaded.append(f"s3://{MINIO_BUCKET}/{obj}")

        log.info("[idealista_dev_dlt] audit upload complete: %d files (override=%s)",
                 len(uploaded), bool(override))
        return {"uploaded": uploaded, "ts": ts, "override_used": bool(override)}

    @task()
    def load_facts(**context) -> dict:
        """SCD2 facts + heartbeat sidecars. Hard fail on schema-contract violation.

        With Pass 3 on the RE API (structured JSON, faster than HTML render)
        and max_workers=4, a full 7-distrito load completes in ~15-25 min.

        target_areas_override Param threads through to the source factory —
        no module-state mutation. None = use module-level TARGET_AREAS.
        """
        _set_zenrows_env()
        override = (context.get("params") or {}).get("target_areas_override") or None

        pipeline = dlt.pipeline(
            pipeline_name="idealista_developments_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR,
        )
        info = pipeline.run(
            idealista_developments_facts_source(target_areas=override)
        )
        log.info("[idealista_dev_dlt] facts load: %s", info)

        counters = get_pass3_counters()
        log.info(
            "[idealista_dev_dlt] Pass 3 counters: total=%d stubs=%d errors=%d",
            counters["total"], counters["stubs"], counters["errors"],
        )
        return {
            "load_id": pipeline.last_trace.last_load_info.loads_ids[-1],
            "pass3_total": counters["total"],
            "pass3_stubs": counters["stubs"],
            "pass3_errors": counters["errors"],
            "override_used": bool(override),
        }

    @task()
    def load_plots(**context) -> dict:
        """Plots SCD2 + heartbeat. Independent of dev+units load — runs in parallel.

        Uses RE API for both passes (discovery + detail), so no Universal Scraper
        cost. ~$5/run for full 7-distrito scope (~3,000 plots × $0.0015).
        """
        _set_zenrows_env()
        override = (context.get("params") or {}).get("target_areas_override") or None

        pipeline = dlt.pipeline(
            pipeline_name="idealista_plots_facts",
            destination=dlt.destinations.postgres(credentials=_postgres_credentials()),
            dataset_name=DATASET_NAME,
            pipelines_dir=PIPELINES_DIR_PLOTS,
        )
        info = pipeline.run(
            idealista_plots_facts_source(target_areas=override)
        )
        log.info("[idealista_dev_dlt] plots load: %s", info)

        counters = get_plots_pass2_counters()
        log.info(
            "[idealista_dev_dlt] Plots Pass 2 counters: total=%d stubs=%d",
            counters["total"], counters["stubs"],
        )
        return {
            "load_id": pipeline.last_trace.last_load_info.loads_ids[-1],
            "plots_pass2_total": counters["total"],
            "plots_pass2_stubs": counters["stubs"],
            "override_used": bool(override),
        }

    @task()
    def validate_facts(facts_result: dict, plots_result: dict) -> dict:
        """Assert SCD2 facts landed: _dlt_loads OK, counts in band, Pass 2/3 gates.

        Devs+units gates (from facts_result):
          Pass 2 floor: ≥80% of devs have _has_detail
          Pass 3 floor: ≥95% of Pass 2 unit_links land in development_units
          Pass 3 stub ceiling: <10%, error ceiling: <5%
        Plots gates (from plots_result):
          Plots row count band [500, 10000] when no override
          Plots stub ceiling: <10%
        """
        import psycopg2

        creds = _postgres_credentials()
        conn = psycopg2.connect(
            host=creds["host"], port=creds["port"], dbname=creds["database"],
            user=creds["username"], password=creds["password"],
        )
        try:
            with conn.cursor() as cur:
                load_id = facts_result["load_id"]
                override_used = facts_result.get("override_used", False)
                cur.execute(
                    f"SELECT status FROM {DATASET_NAME}._dlt_loads WHERE load_id = %s",
                    (load_id,),
                )
                rows = cur.fetchall()
                if not rows or any(r[0] != 0 for r in rows):
                    raise RuntimeError(
                        f"_dlt_loads for load_id={load_id} not status=0: {rows}"
                    )

                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.idealista_developments "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                devs_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.idealista_development_units "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                units_current = cur.fetchone()[0]
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.idealista_developments "
                    f"WHERE _dlt_valid_to IS NULL AND _has_detail = TRUE"
                )
                devs_enriched = cur.fetchone()[0]

                # Row-count bands. When the override Param is in use (e.g. Aveiro
                # test) the bands don't apply — the override is for testing.
                if not override_used:
                    if devs_current < 200 or devs_current > 3000:
                        raise RuntimeError(
                            f"developments current-state row count {devs_current} "
                            f"outside expected band [200, 3000]"
                        )
                    if units_current < 500 or units_current > 50_000:
                        raise RuntimeError(
                            f"units current-state row count {units_current} "
                            f"outside expected band [500, 50000]"
                        )

                # Pass 2 enrichment floor
                if devs_current and devs_enriched < PASS2_ENRICHMENT_FLOOR * devs_current:
                    raise RuntimeError(
                        f"Pass 2 enrichment too low: {devs_enriched}/{devs_current} devs "
                        f"have detail (floor={PASS2_ENRICHMENT_FLOOR:.0%}). "
                        f"Check _parse_development_detail selectors — DataDome may have shifted."
                    )

                # Pass 3 metrics from XCom (counters captured during load_facts)
                pass3_total = facts_result.get("pass3_total", 0)
                pass3_stubs = facts_result.get("pass3_stubs", 0)
                pass3_errors = facts_result.get("pass3_errors", 0)

                if pass3_total > 0:
                    # Enrichment floor: units_current / Pass 3 attempts.
                    # Stubs are SKIPPED from units_current intentionally, so the
                    # achievable upper bound is (pass3_total - pass3_stubs).
                    achievable = pass3_total - pass3_stubs
                    if achievable > 0 and units_current < PASS3_ENRICHMENT_FLOOR * achievable:
                        raise RuntimeError(
                            f"Pass 3 enrichment too low: units_current={units_current} "
                            f"vs achievable={achievable} "
                            f"(pass3_total={pass3_total}, stubs={pass3_stubs}). "
                            f"Floor={PASS3_ENRICHMENT_FLOOR:.0%}."
                        )

                    stub_rate = pass3_stubs / pass3_total
                    if stub_rate > PASS3_STUB_RATE_CEILING:
                        raise RuntimeError(
                            f"Pass 3 stub rate too high: {stub_rate:.1%} "
                            f"(ceiling={PASS3_STUB_RATE_CEILING:.0%}). "
                            f"Likely cross-country tld leakage or systemic deactivations."
                        )

                    error_rate = pass3_errors / pass3_total
                    if error_rate > PASS3_ERROR_RATE_CEILING:
                        raise RuntimeError(
                            f"Pass 3 RE API error rate too high: {error_rate:.1%} "
                            f"(ceiling={PASS3_ERROR_RATE_CEILING:.0%}). "
                            f"Likely 429 rate limiting — drop PASS2_PASS3_MAX_WORKERS to 2."
                        )

                # ----- Plots gates -----
                cur.execute(
                    f"SELECT count(*) FROM {DATASET_NAME}.idealista_plots "
                    f"WHERE _dlt_valid_to IS NULL"
                )
                plots_current = cur.fetchone()[0]
                plots_load_id = plots_result["load_id"]
                cur.execute(
                    f"SELECT status FROM {DATASET_NAME}._dlt_loads WHERE load_id = %s",
                    (plots_load_id,),
                )
                plot_load_rows = cur.fetchall()
                if not plot_load_rows or any(r[0] != 0 for r in plot_load_rows):
                    raise RuntimeError(
                        f"plots _dlt_loads for load_id={plots_load_id} not status=0: {plot_load_rows}"
                    )
                if not override_used and (plots_current < 500 or plots_current > 10_000):
                    raise RuntimeError(
                        f"plots current-state row count {plots_current} "
                        f"outside expected band [500, 10000]"
                    )
                plots_pass2_total = plots_result.get("plots_pass2_total", 0)
                plots_pass2_stubs = plots_result.get("plots_pass2_stubs", 0)
                if plots_pass2_total > 0:
                    plots_stub_rate = plots_pass2_stubs / plots_pass2_total
                    if plots_stub_rate > PASS3_STUB_RATE_CEILING:
                        raise RuntimeError(
                            f"Plots stub rate too high: {plots_stub_rate:.1%} "
                            f"(ceiling={PASS3_STUB_RATE_CEILING:.0%})."
                        )

                log.info(
                    "[idealista_dev_dlt] validation OK: developments=%d (%d enriched), "
                    "units=%d, pass3_total=%d stubs=%d errors=%d, plots=%d (pass2_total=%d stubs=%d), "
                    "load_id=%s, plots_load_id=%s, override_used=%s",
                    devs_current, devs_enriched, units_current,
                    pass3_total, pass3_stubs, pass3_errors,
                    plots_current, plots_pass2_total, plots_pass2_stubs,
                    load_id, plots_load_id, override_used,
                )
                return {
                    "load_id": load_id,
                    "plots_load_id": plots_load_id,
                    "developments_current": devs_current,
                    "developments_enriched": devs_enriched,
                    "units_current": units_current,
                    "pass3_total": pass3_total,
                    "pass3_stubs": pass3_stubs,
                    "pass3_errors": pass3_errors,
                    "plots_current": plots_current,
                    "plots_pass2_total": plots_pass2_total,
                    "plots_pass2_stubs": plots_pass2_stubs,
                    "override_used": override_used,
                }
        finally:
            conn.close()

    audit = audit_to_minio()
    facts = load_facts()
    plots = load_plots()
    validation = validate_facts(facts, plots)

    audit >> [facts, plots]
    facts >> validation
    plots >> validation
