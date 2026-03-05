"""
Idealista Ingestion DAG — ZenRows API to MinIO

Two-phase crawl: discovery (search result pages) → property detail.
Stores raw JSONL in MinIO at:
  raw/idealista/discovery/{operation}/{distrito}/{YYYYMMDD}.jsonl
  raw/idealista/detail/{operation}/{distrito}/{YYYYMMDD}.jsonl

Incremental: detail phase skips listings already in bronze within
DETAIL_REFRESH_DAYS (default 30). Previous detail data is carried forward
from MinIO. Force full re-fetch by setting force_full_refresh=true in
trigger config.

Schedule: daily at 03:00 UTC (catchup=False).
Trigger with config to run a single segment:
  {"distrito": "beja", "operation": "sale"}
"""

from __future__ import annotations

import json
import logging
import os


def _jsonl_line(obj: dict) -> str:
    """Serialize dict to a JSONL-safe line (escapes U+2028/U+2029)."""
    line = json.dumps(obj, ensure_ascii=False)
    return line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
import shutil
import tempfile
import time
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)


def _get_known_property_ids(detail_refresh_days: int) -> set[str]:
    """
    Query bronze table for property_ids scraped within the refresh window.
    Returns a set of property_id strings that do NOT need re-fetching.
    """
    import psycopg2
    from airflow.models import Variable

    try:
        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=detail_refresh_days)).isoformat()
        cur.execute(
            "SELECT DISTINCT _property_id "
            "FROM bronze_listings.raw_idealista "
            "WHERE _scrape_date >= %s",
            (cutoff,),
        )
        known = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()
        log.info(
            "[idealista] Found %d known property_ids in bronze (last %d days)",
            len(known),
            detail_refresh_days,
        )
        return known
    except Exception as exc:
        # Table may not exist on first run
        log.warning(
            "[idealista] Could not query bronze table (first run?): %s", exc
        )
        return set()


def _find_previous_detail(
    minio_client, bucket: str, prefix: str, operation: str, distrito: str
) -> dict[str, dict]:
    """
    Find the most recent detail JSONL for this segment in MinIO.
    Returns a dict mapping property_id → detail JSON object.
    Used to carry forward data for skipped listings.
    """
    detail_prefix = f"{prefix}/detail/{operation}/{distrito}/"
    objects = list(
        minio_client.list_objects(bucket, prefix=detail_prefix, recursive=True)
    )
    jsonl_files = [
        o for o in objects if o.object_name.endswith(".jsonl")
    ]
    if not jsonl_files:
        return {}

    # Latest file by name (YYYYMMDD sorts lexicographically)
    latest = sorted(jsonl_files, key=lambda o: o.object_name)[-1]

    resp = minio_client.get_object(bucket, latest.object_name)
    raw_bytes = resp.read()
    resp.close()
    resp.release_conn()

    previous = {}
    for line in raw_bytes.decode("utf-8").split("\n"):
        line = line.strip()
        if not line:
            continue
        detail = json.loads(line)
        pid = detail.get("_property_id") or detail.get("property_id")
        if pid:
            previous[str(pid)] = detail

    log.info(
        "[idealista] %s/%s: loaded %d previous details from %s",
        operation,
        distrito,
        len(previous),
        latest.object_name,
    )
    return previous


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param
    from airflow.operators.trigger_dagrun import TriggerDagRunOperator

    default_args = {
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    @dag(
        dag_id="idealista_ingestion",
        description=(
            "Idealista listing ingestion via ZenRows API. "
            "Crawls Portuguese distritos for sale and rent. "
            "Stores discovery + detail JSONL in MinIO raw layer."
        ),
        schedule="0 3 * * *",
        start_date=datetime(2025, 1, 1),
        catchup=False,
        max_active_runs=1,
        max_active_tasks=4,
        default_args=default_args,
        params={
            "distrito": Param(
                default="all",
                description=(
                    "Single distrito to crawl (e.g. 'beja'), or 'all' for all 18."
                ),
                type="string",
            ),
            "operation": Param(
                default="all",
                description=(
                    "Operation type: 'sale', 'rent', or 'all' for both."
                ),
                type="string",
            ),
            "force_full_refresh": Param(
                default=False,
                description=(
                    "Force re-fetch of ALL listing details, ignoring incremental cache."
                ),
                type="boolean",
            ),
        },
        tags=["ingestion", "api", "idealista", "minio", "listings"],
    )
    def idealista_ingestion():

        @task()
        def check_zenrows_api(**context) -> dict:
            """Validate ZenRows API key with a single test discovery call."""
            import requests
            from airflow.models import Variable

            from pipelines.api.idealista.idealista_config import (
                DISTRITO_SEARCH_URLS,
                REQUEST_TIMEOUT_SECONDS,
                ZENROWS_DISCOVERY_URL,
            )

            api_key = Variable.get("ZENROWS_API_KEY")

            # Use the first distrito that will actually be crawled for the test
            params_distrito = context["params"].get("distrito", "all")
            if params_distrito != "all" and params_distrito in DISTRITO_SEARCH_URLS:
                test_distrito = params_distrito
            else:
                test_distrito = "aveiro"

            test_url = DISTRITO_SEARCH_URLS[test_distrito]["sale"]
            params = {"url": test_url, "page": 1, "apikey": api_key}

            resp = requests.get(
                ZENROWS_DISCOVERY_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list):
                item_count = len(data)
            elif isinstance(data, dict):
                item_count = len(
                    data.get("property_list") or data.get("data") or []
                )
            else:
                item_count = 0
            log.info(
                "[idealista] API check passed — got %d items from %s/sale test",
                item_count,
                test_distrito,
            )
            return {"status": "ok", "test_items": item_count}

        @task()
        def build_segments(_api_check: dict, **context) -> list[dict]:
            """Build segment dicts, filtered by trigger params."""
            from pipelines.api.idealista.idealista_config import (
                ACTIVE_DISTRITOS,
                DETAIL_REFRESH_DAYS,
                DISTRITO_SEARCH_URLS,
                OPERATIONS,
            )

            param_distrito = context["params"].get("distrito", "all")
            param_operation = context["params"].get("operation", "all")
            force_full = context["params"].get("force_full_refresh", False)

            # Determine which distritos/operations to crawl
            if param_distrito != "all":
                if param_distrito not in DISTRITO_SEARCH_URLS:
                    raise ValueError(
                        f"Unknown distrito '{param_distrito}'. "
                        f"Valid: {list(DISTRITO_SEARCH_URLS.keys())}"
                    )
                distritos = {param_distrito: DISTRITO_SEARCH_URLS[param_distrito]}
            elif ACTIVE_DISTRITOS is not None:
                distritos = {
                    d: DISTRITO_SEARCH_URLS[d]
                    for d in ACTIVE_DISTRITOS
                    if d in DISTRITO_SEARCH_URLS
                }
            else:
                distritos = DISTRITO_SEARCH_URLS

            if param_operation != "all":
                if param_operation not in OPERATIONS:
                    raise ValueError(
                        f"Unknown operation '{param_operation}'. Valid: {OPERATIONS}"
                    )
                operations = [param_operation]
            else:
                operations = OPERATIONS

            # Get known property_ids for incremental logic
            if force_full:
                known_ids = set()
                log.info("[idealista] Force full refresh — skipping incremental check")
            else:
                known_ids = _get_known_property_ids(DETAIL_REFRESH_DAYS)

            segments = []
            for distrito, ops in distritos.items():
                for operation in operations:
                    segments.append(
                        {
                            "operation": operation,
                            "distrito": distrito,
                            "search_url": ops[operation],
                            "known_ids_count": len(known_ids),
                            "force_full": force_full,
                        }
                    )

            log.info(
                "[idealista] Built %d segments (distrito=%s, operation=%s, "
                "known_ids=%d, force_full=%s)",
                len(segments),
                param_distrito,
                param_operation,
                len(known_ids),
                force_full,
            )
            return segments

        @task()
        def crawl_discovery(segment: dict) -> dict:
            """
            Phase 1: Paginate ZenRows Discovery for one distrito/operation.
            Fetches all pages (20 listings/page) until empty or 1,800 cap.
            Writes JSONL to MinIO.
            """
            import requests
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.idealista.idealista_config import (
                DISCOVERY_RATE_LIMIT_SECONDS,
                MINIO_BUCKET,
                MINIO_PREFIX,
                REQUEST_TIMEOUT_SECONDS,
                ZENROWS_DISCOVERY_URL,
            )

            api_key = Variable.get("ZENROWS_API_KEY")
            operation = segment["operation"]
            distrito = segment["distrito"]
            search_url = segment["search_url"]
            scrape_date = date.today().strftime("%Y%m%d")

            minio_client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            if not minio_client.bucket_exists(MINIO_BUCKET):
                minio_client.make_bucket(MINIO_BUCKET)

            all_items = []
            page = 1
            MAX_PAGES = 90  # 90 × 20 = 1,800 listing cap

            while page <= MAX_PAGES:
                params = {"url": search_url, "page": page, "apikey": api_key}
                resp = requests.get(
                    ZENROWS_DISCOVERY_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                items = resp.json()

                if isinstance(items, list):
                    page_items = items
                elif isinstance(items, dict):
                    # ZenRows wraps results: {"pagination": {...}, "property_list": [...]}
                    page_items = (
                        items.get("property_list")
                        or items.get("data")
                        or []
                    )
                else:
                    break

                if not page_items:
                    log.info(
                        "[idealista] %s/%s: empty page %d — stopping",
                        operation,
                        distrito,
                        page,
                    )
                    break

                for item in page_items:
                    item["_distrito"] = distrito
                    item["_operation"] = operation
                    item["_scrape_date"] = scrape_date
                    item["_page"] = page
                all_items.extend(page_items)

                log.info(
                    "[idealista] %s/%s: page %d → %d items (total: %d)",
                    operation,
                    distrito,
                    page,
                    len(page_items),
                    len(all_items),
                )
                page += 1
                time.sleep(DISCOVERY_RATE_LIMIT_SECONDS)

            if len(all_items) >= 1800:
                log.warning(
                    "[idealista] %s/%s: hit 1,800 listing cap — "
                    "consider splitting by municipality",
                    operation,
                    distrito,
                )

            # Write JSONL to temp file then upload to MinIO
            tmp_dir = tempfile.mkdtemp(prefix="idealista_disc_")
            local_path = os.path.join(
                tmp_dir, f"{distrito}_{operation}_{scrape_date}_discovery.jsonl"
            )
            with open(local_path, "w", encoding="utf-8") as f:
                for item in all_items:
                    f.write(_jsonl_line(item) + "\n")

            minio_object = (
                f"{MINIO_PREFIX}/discovery/{operation}/{distrito}/{scrape_date}.jsonl"
            )
            minio_client.fput_object(
                bucket_name=MINIO_BUCKET,
                object_name=minio_object,
                file_path=local_path,
                content_type="application/x-ndjson",
                metadata={
                    "x-amz-meta-source": "idealista",
                    "x-amz-meta-operation": operation,
                    "x-amz-meta-distrito": distrito,
                    "x-amz-meta-scrape-date": scrape_date,
                    "x-amz-meta-listing-count": str(len(all_items)),
                },
            )
            shutil.rmtree(tmp_dir)

            log.info(
                "[idealista] %s/%s: discovery done — %d listings → s3://%s/%s",
                operation,
                distrito,
                len(all_items),
                MINIO_BUCKET,
                minio_object,
            )
            return {
                "operation": operation,
                "distrito": distrito,
                "discovery_minio_path": minio_object,
                "listing_count": len(all_items),
                "scrape_date": scrape_date,
                "force_full": segment.get("force_full", False),
            }

        @task()
        def crawl_details(discovery_result: dict) -> dict:
            """
            Phase 2: Fetch property detail for discovered listings.

            Incremental logic:
            - Query bronze for property_ids scraped within DETAIL_REFRESH_DAYS
            - Only fetch detail for NEW listings not in that set
            - Carry forward previous detail data from MinIO for skipped listings
            - Force full refresh overrides this and fetches everything
            """
            import requests
            from airflow.models import Variable
            from minio import Minio

            from pipelines.api.idealista.idealista_config import (
                DETAIL_RATE_LIMIT_SECONDS,
                DETAIL_REFRESH_DAYS,
                MINIO_BUCKET,
                MINIO_PREFIX,
                REQUEST_TIMEOUT_SECONDS,
                ZENROWS_DETAIL_URL,
            )

            api_key = Variable.get("ZENROWS_API_KEY")
            operation = discovery_result["operation"]
            distrito = discovery_result["distrito"]
            scrape_date = discovery_result["scrape_date"]
            discovery_path = discovery_result["discovery_minio_path"]
            force_full = discovery_result.get("force_full", False)

            minio_client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            # Read discovery JSONL from MinIO
            resp = minio_client.get_object(MINIO_BUCKET, discovery_path)
            raw_bytes = resp.read()
            resp.close()
            resp.release_conn()

            discovery_items = [
                json.loads(line)
                for line in raw_bytes.decode("utf-8").split("\n")
                if line.strip()
            ]
            all_ids = [
                str(item["property_id"])
                for item in discovery_items
                if item.get("property_id")
            ]

            # Determine which IDs need fetching
            if force_full:
                ids_to_fetch = all_ids
                ids_to_skip = set()
                previous_details = {}
                log.info(
                    "[idealista] %s/%s: force full — fetching all %d listings",
                    operation,
                    distrito,
                    len(ids_to_fetch),
                )
            else:
                known_ids = _get_known_property_ids(DETAIL_REFRESH_DAYS)
                ids_to_fetch = [pid for pid in all_ids if pid not in known_ids]
                ids_to_skip = {pid for pid in all_ids if pid in known_ids}

                # Load previous detail data for skipped IDs
                if ids_to_skip:
                    previous_details = _find_previous_detail(
                        minio_client, MINIO_BUCKET, MINIO_PREFIX, operation, distrito
                    )
                else:
                    previous_details = {}

                log.info(
                    "[idealista] %s/%s: %d total, %d new to fetch, "
                    "%d skipped (in bronze last %d days), %d previous details loaded",
                    operation,
                    distrito,
                    len(all_ids),
                    len(ids_to_fetch),
                    len(ids_to_skip),
                    DETAIL_REFRESH_DAYS,
                    len(previous_details),
                )

            # Fetch detail for new listings
            tmp_dir = tempfile.mkdtemp(prefix="idealista_det_")
            local_path = os.path.join(
                tmp_dir, f"{distrito}_{operation}_{scrape_date}_detail.jsonl"
            )
            detail_count = 0
            carried_forward = 0
            errors = 0

            with open(local_path, "w", encoding="utf-8") as f:
                # Write carried-forward details first
                for pid in ids_to_skip:
                    if pid in previous_details:
                        prev = previous_details[pid]
                        prev["_scrape_date"] = scrape_date
                        prev["_carried_forward"] = True
                        f.write(_jsonl_line(prev) + "\n")
                        carried_forward += 1

                # Fetch new details from ZenRows
                for prop_id in ids_to_fetch:
                    url = ZENROWS_DETAIL_URL.format(property_id=prop_id)
                    try:
                        detail_resp = requests.get(
                            url,
                            params={"apikey": api_key, "tld": ".pt"},
                            timeout=REQUEST_TIMEOUT_SECONDS,
                        )
                        detail_resp.raise_for_status()
                        detail = detail_resp.json()
                        detail["_property_id"] = prop_id
                        detail["_distrito"] = distrito
                        detail["_operation"] = operation
                        detail["_scrape_date"] = scrape_date
                        detail["_carried_forward"] = False
                        f.write(_jsonl_line(detail) + "\n")
                        detail_count += 1
                    except Exception as exc:
                        log.warning(
                            "[idealista] %s/%s: detail fetch failed for %s — %s",
                            operation,
                            distrito,
                            prop_id,
                            exc,
                        )
                        errors += 1
                    time.sleep(DETAIL_RATE_LIMIT_SECONDS)

            # Upload detail JSONL to MinIO
            minio_object = (
                f"{MINIO_PREFIX}/detail/{operation}/{distrito}/{scrape_date}.jsonl"
            )
            minio_client.fput_object(
                bucket_name=MINIO_BUCKET,
                object_name=minio_object,
                file_path=local_path,
                content_type="application/x-ndjson",
                metadata={
                    "x-amz-meta-source": "idealista",
                    "x-amz-meta-operation": operation,
                    "x-amz-meta-distrito": distrito,
                    "x-amz-meta-scrape-date": scrape_date,
                    "x-amz-meta-detail-fetched": str(detail_count),
                    "x-amz-meta-detail-carried-forward": str(carried_forward),
                    "x-amz-meta-errors": str(errors),
                },
            )
            shutil.rmtree(tmp_dir)

            log.info(
                "[idealista] %s/%s: detail done — %d fetched, %d carried forward, "
                "%d errors → s3://%s/%s",
                operation,
                distrito,
                detail_count,
                carried_forward,
                errors,
                MINIO_BUCKET,
                minio_object,
            )
            return {
                "operation": operation,
                "distrito": distrito,
                "detail_minio_path": minio_object,
                "detail_count": detail_count,
                "carried_forward": carried_forward,
                "errors": errors,
                "scrape_date": scrape_date,
            }

        @task(trigger_rule="all_done")
        def log_run_summary(detail_results: list[dict]) -> dict:
            """Log a structured summary of the entire ingestion run."""
            total_fetched = sum(r.get("detail_count", 0) for r in detail_results)
            total_carried = sum(r.get("carried_forward", 0) for r in detail_results)
            total_errors = sum(r.get("errors", 0) for r in detail_results)
            log.info("=" * 60)
            log.info("IDEALISTA INGESTION COMPLETE")
            log.info("  Details fetched (new)  : %d", total_fetched)
            log.info("  Details carried forward: %d", total_carried)
            log.info("  Total listings         : %d", total_fetched + total_carried)
            log.info("  Errors                 : %d", total_errors)
            log.info("  Segments               : %d", len(detail_results))
            log.info("=" * 60)
            for r in detail_results:
                log.info(
                    "  [%s/%s] %d fetched, %d carried, %d errors → %s",
                    r["operation"],
                    r["distrito"],
                    r.get("detail_count", 0),
                    r.get("carried_forward", 0),
                    r.get("errors", 0),
                    r.get("detail_minio_path", "n/a"),
                )
            return {
                "total_fetched": total_fetched,
                "total_carried_forward": total_carried,
                "total_errors": total_errors,
            }

        # --- Task wiring ---
        api_check = check_zenrows_api()
        segments = build_segments(api_check)
        discovery_results = crawl_discovery.expand(segment=segments)
        detail_results = crawl_details.expand(discovery_result=discovery_results)
        summary = log_run_summary(detail_results)

        trigger_bronze = TriggerDagRunOperator(
            task_id="trigger_bronze_load",
            trigger_dag_id="idealista_bronze_load",
            wait_for_completion=True,
            reset_dag_run=True,
        )
        summary >> trigger_bronze

    return idealista_ingestion()


dag = _create_dag()
