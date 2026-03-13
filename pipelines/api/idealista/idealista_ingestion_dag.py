"""
Idealista Ingestion DAG — ZenRows API to MinIO

Two-phase crawl: discovery (search result pages) → property detail.
Stores raw JSONL in MinIO at:
  raw/idealista/discovery/{operation}/{distrito}/{YYYYMMDD}.jsonl
  raw/idealista/detail/{operation}/{distrito}/{YYYYMMDD}.jsonl

Incremental: detail phase skips listings already in bronze within
detail_refresh_days (default 30). Previous detail data is carried forward
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
import shutil
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def _jsonl_line(obj: dict) -> str:
    """Serialize dict to a JSONL-safe line (escapes U+2028/U+2029)."""
    line = json.dumps(obj, ensure_ascii=False)
    return line.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _extract_items(data) -> list:
    """Extract property list from a ZenRows discovery response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("property_list") or data.get("data") or []
    return []


def _get_known_property_ids(config, detail_refresh_days: int) -> set[str]:
    """
    Query bronze table for property_ids scraped within the refresh window.
    Returns a set of property_id strings that do NOT need re-fetching.
    """
    import psycopg2
    from airflow.models import Variable

    conn = None
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
            f"FROM {config.bronze_schema_table} "
            "WHERE _scrape_date >= %s",
            (cutoff,),
        )
        known = {row[0] for row in cur.fetchall()}
        cur.close()
        log.info(
            "[%s] Found %d known property_ids in bronze (last %d days)",
            config.source_name,
            len(known),
            detail_refresh_days,
        )
        return known
    except Exception as exc:
        log.warning(
            "[%s] Could not query bronze table (first run?): %s",
            config.source_name,
            exc,
        )
        return set()
    finally:
        if conn:
            conn.close()


def _find_previous_detail(
    config, minio_client, bucket: str, prefix: str, operation: str,
    distrito: str, concelho: str | None = None, exclude_date: str | None = None,
) -> dict[str, dict]:
    """
    Find the most recent detail JSONL for this segment in MinIO.
    Returns a dict mapping property_id → detail JSON object.
    Used to carry forward data for skipped listings.
    """
    if concelho:
        detail_prefix = f"{prefix}/detail/{operation}/{distrito}/{concelho}/"
    else:
        detail_prefix = f"{prefix}/detail/{operation}/{distrito}/"
    objects = list(
        minio_client.list_objects(bucket, prefix=detail_prefix, recursive=True)
    )
    jsonl_files = [
        o for o in objects if o.object_name.endswith(".jsonl")
    ]
    if not jsonl_files:
        return {}

    # Filter to same path depth to avoid mixing distrito-level and concelho-level files
    expected_depth = detail_prefix.count("/")
    jsonl_files = [
        o for o in jsonl_files
        if o.object_name.count("/") == expected_depth
    ]
    if not jsonl_files:
        return {}

    # Exclude today's (possibly empty) file so we load a real previous day
    if exclude_date:
        jsonl_files = [
            o for o in jsonl_files
            if not o.object_name.endswith(f"/{exclude_date}.jsonl")
        ]
        if not jsonl_files:
            return {}

    # Sort by filename (YYYYMMDD.jsonl) to get the latest date
    latest = sorted(jsonl_files, key=lambda o: o.object_name)[-1]

    resp = minio_client.get_object(bucket, latest.object_name)
    try:
        raw_bytes = resp.read()
    finally:
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
        "[%s] %s/%s: loaded %d previous details from %s",
        config.source_name,
        operation,
        distrito,
        len(previous),
        latest.object_name,
    )
    return previous


def _create_dag():
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    from pipelines.api.idealista.idealista_config import IDEALISTA_CONFIG as config

    default_args = {
        "owner": "data-engineering",
        "retries": config.retries,
        "retry_delay": timedelta(minutes=config.retry_delay_minutes),
    }

    @dag(
        dag_id=config.dag_id,
        description=config.description,
        schedule=config.schedule,
        start_date=config.start_date,
        catchup=False,
        max_active_runs=config.max_active_runs,
        max_active_tasks=config.max_active_tasks,
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
            "concelho": Param(
                default="all",
                description=(
                    "Single concelho slug to crawl (e.g. 'agueda'), "
                    "or 'all' for all concelhos in the selected distrito(s)."
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
        tags=["ingestion", "api", "minio", "listings"] + config.tags,
    )
    def idealista_ingestion():

        @task()
        def check_api_availability(**context) -> dict:
            """Validate ZenRows API key with a single test discovery call."""
            import requests
            from airflow.models import Variable

            api_key = Variable.get("ZENROWS_API_KEY")

            params_distrito = context["params"].get("distrito", "all")
            if params_distrito != "all" and params_distrito in config.distrito_search_urls:
                test_distrito = params_distrito
            else:
                test_distrito = "aveiro"

            test_url = config.distrito_search_urls[test_distrito]["sale"]
            params = {"url": test_url, "page": 1, "apikey": api_key}

            resp = requests.get(
                config.discovery_url,
                params=params,
                timeout=config.request_timeout_seconds,
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
                "[%s] API check passed — got %d items from %s/sale test",
                config.source_name,
                item_count,
                test_distrito,
            )
            return {"status": "ok", "test_items": item_count}

        @task()
        def build_segments(_api_check: dict, **context) -> list[dict]:
            """Build segment dicts — one per concelho × operation."""
            from pipelines.api.idealista.idealista_config import (
                build_idealista_url,
                fetch_concelho_mapping,
                to_idealista_slug,
            )

            param_distrito = context["params"].get("distrito", "all")
            param_operation = context["params"].get("operation", "all")
            param_concelho = context["params"].get("concelho", "all")
            force_full = context["params"].get("force_full_refresh", False)

            if param_operation != "all":
                if param_operation not in config.operations:
                    raise ValueError(
                        f"Unknown operation '{param_operation}'. Valid: {config.operations}"
                    )
                operations = [param_operation]
            else:
                operations = config.operations

            if force_full:
                known_ids = set()
                log.info("[%s] Force full refresh — skipping incremental check", config.source_name)
            else:
                known_ids = _get_known_property_ids(config, config.detail_refresh_days)

            segments = []

            if config.crawl_level == "concelho":
                # Determine active distritos
                if param_distrito != "all":
                    active = [param_distrito]
                elif config.active_distritos is not None:
                    active = config.active_distritos
                else:
                    active = None  # all distritos

                concelho_mapping = fetch_concelho_mapping(active)
                if not concelho_mapping:
                    raise ValueError(
                        f"No concelhos found in dim_geography for distritos={active}. "
                        "Has dim_geography been built?"
                    )

                # Filter to single concelho if specified
                if param_concelho != "all":
                    concelho_mapping = [
                        m for m in concelho_mapping
                        if to_idealista_slug(m["concelho_name"]) == param_concelho
                    ]
                    if not concelho_mapping:
                        raise ValueError(f"Unknown concelho '{param_concelho}'.")

                for entry in concelho_mapping:
                    distrito_slug = to_idealista_slug(entry["distrito_name"])
                    concelho_slug = to_idealista_slug(entry["concelho_name"])
                    for operation in operations:
                        segments.append({
                            "operation": operation,
                            "distrito": distrito_slug,
                            "concelho": concelho_slug,
                            "search_url": build_idealista_url(
                                operation, entry["distrito_name"], entry["concelho_name"]
                            ),
                            "known_ids_count": len(known_ids),
                            "force_full": force_full,
                        })
            else:
                # Legacy distrito-level segments
                if param_distrito != "all":
                    if param_distrito not in config.distrito_search_urls:
                        raise ValueError(
                            f"Unknown distrito '{param_distrito}'. "
                            f"Valid: {list(config.distrito_search_urls.keys())}"
                        )
                    distritos = {param_distrito: config.distrito_search_urls[param_distrito]}
                elif config.active_distritos is not None:
                    distritos = {
                        d: config.distrito_search_urls[d]
                        for d in config.active_distritos
                        if d in config.distrito_search_urls
                    }
                else:
                    distritos = config.distrito_search_urls

                for distrito, ops in distritos.items():
                    for operation in operations:
                        segments.append({
                            "operation": operation,
                            "distrito": distrito,
                            "concelho": None,
                            "search_url": ops[operation],
                            "known_ids_count": len(known_ids),
                            "force_full": force_full,
                        })

            log.info(
                "[%s] Built %d segments (level=%s, distrito=%s, "
                "concelho=%s, operation=%s, known_ids=%d)",
                config.source_name,
                len(segments),
                config.crawl_level,
                param_distrito,
                param_concelho,
                param_operation,
                len(known_ids),
            )
            return segments

        @task()
        def crawl_discovery(segment: dict) -> dict:
            """
            Phase 1: Paginate ZenRows Discovery for one distrito/operation.
            Fetches all pages (20 listings/page) until empty or listing cap.
            Writes JSONL to MinIO.
            """
            import requests
            from airflow.models import Variable
            from minio import Minio
            from tenacity import (
                retry,
                retry_if_exception_type,
                stop_after_attempt,
                wait_exponential,
            )

            @retry(
                stop=stop_after_attempt(config.max_retries),
                wait=wait_exponential(
                    multiplier=1, min=config.retry_backoff_seconds, max=60
                ),
                retry=retry_if_exception_type(
                    (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.HTTPError,
                    )
                ),
                reraise=True,
            )
            def _fetch_page(url, params, timeout):
                resp = requests.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp

            api_key = Variable.get("ZENROWS_API_KEY")
            operation = segment["operation"]
            distrito = segment["distrito"]
            concelho = segment.get("concelho")
            search_url = segment["search_url"]
            scrape_date = date.today().strftime("%Y%m%d")
            segment_label = f"{distrito}/{concelho}" if concelho else distrito

            minio_client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )
            if not minio_client.bucket_exists(config.minio_bucket):
                minio_client.make_bucket(config.minio_bucket)

            all_items = []
            page = 1

            while page <= config.max_discovery_pages:
                params = {"url": search_url, "page": page, "apikey": api_key}
                resp = _fetch_page(
                    config.discovery_url, params, config.request_timeout_seconds
                )
                page_items = _extract_items(resp.json())

                if not page_items:
                    log.info(
                        "[%s] %s/%s: empty page %d — stopping",
                        config.source_name,
                        operation,
                        segment_label,
                        page,
                    )
                    break

                for item in page_items:
                    item["_distrito"] = distrito
                    item["_concelho"] = concelho or ""
                    item["_operation"] = operation
                    item["_scrape_date"] = scrape_date
                    item["_page"] = page
                all_items.extend(page_items)

                log.info(
                    "[%s] %s/%s: page %d → %d items (total: %d)",
                    config.source_name,
                    operation,
                    segment_label,
                    page,
                    len(page_items),
                    len(all_items),
                )
                page += 1
                time.sleep(config.discovery_rate_limit_seconds)

            # page was incremented after the last successful fetch, so
            # (page - 1) is the number of pages actually fetched.
            if page - 1 >= config.max_discovery_pages:
                log.warning(
                    "[%s] %s/%s: hit page cap (%d pages, %d listings) — "
                    "some listings may be missing",
                    config.source_name,
                    operation,
                    segment_label,
                    page - 1,
                    len(all_items),
                )

            # Deduplicate — ZenRows recycles results after ~50 pages
            seen_ids: set[str] = set()
            unique_items = []
            for item in all_items:
                pid = item.get("property_id")
                if pid and str(pid) not in seen_ids:
                    seen_ids.add(str(pid))
                    unique_items.append(item)
            all_items = unique_items

            # Auto-split by price range if we hit the ~1,000 unique cap
            from pipelines.api.idealista.idealista_config import (
                PRICE_RANGE_BOUNDARIES,
                UNIQUE_CAP_THRESHOLD,
                build_price_filtered_url,
            )

            if len(all_items) >= UNIQUE_CAP_THRESHOLD:
                log.info(
                    "[%s] %s/%s: %d unique items ≥ %d cap threshold — "
                    "re-crawling with %d price-range splits",
                    config.source_name,
                    operation,
                    segment_label,
                    len(all_items),
                    UNIQUE_CAP_THRESHOLD,
                    len(PRICE_RANGE_BOUNDARIES) + 1,
                )

                boundaries = [None] + PRICE_RANGE_BOUNDARIES + [None]
                split_items: list[dict] = []
                split_seen: set[str] = set()

                for i in range(len(boundaries) - 1):
                    p_min, p_max = boundaries[i], boundaries[i + 1]
                    split_url = build_price_filtered_url(search_url, p_min, p_max)
                    range_label = f"{p_min or 0}-{p_max or '∞'}"
                    split_page = 1
                    prev_total = len(split_seen)

                    while split_page <= config.max_discovery_pages:
                        params = {
                            "url": split_url,
                            "page": split_page,
                            "apikey": api_key,
                        }
                        resp = _fetch_page(
                            config.discovery_url,
                            params,
                            config.request_timeout_seconds,
                        )
                        page_items = _extract_items(resp.json())
                        if not page_items:
                            break

                        new_count = 0
                        for item in page_items:
                            pid = item.get("property_id")
                            if pid and str(pid) not in split_seen:
                                split_seen.add(str(pid))
                                item["_distrito"] = distrito
                                item["_concelho"] = concelho or ""
                                item["_operation"] = operation
                                item["_scrape_date"] = scrape_date
                                item["_page"] = split_page
                                split_items.append(item)
                                new_count += 1

                        if new_count == 0:
                            break  # all duplicates — exhausted this range

                        split_page += 1
                        time.sleep(config.discovery_rate_limit_seconds)

                    range_count = len(split_seen) - prev_total
                    log.info(
                        "[%s] %s/%s: price range %s → %d unique items",
                        config.source_name,
                        operation,
                        segment_label,
                        range_label,
                        range_count,
                    )

                log.info(
                    "[%s] %s/%s: price-split total: %d unique (was %d before split)",
                    config.source_name,
                    operation,
                    segment_label,
                    len(split_items),
                    len(all_items),
                )
                all_items = split_items

            # Write JSONL to temp file then upload to MinIO
            tmp_dir = tempfile.mkdtemp(prefix="idealista_disc_")
            local_path = os.path.join(
                tmp_dir, f"{distrito}_{concelho or 'all'}_{operation}_{scrape_date}_discovery.jsonl"
            )
            with open(local_path, "w", encoding="utf-8") as f:
                for item in all_items:
                    f.write(_jsonl_line(item) + "\n")

            if concelho:
                minio_object = (
                    f"{config.minio_prefix}/discovery/{operation}/{distrito}/{concelho}/{scrape_date}.jsonl"
                )
            else:
                minio_object = (
                    f"{config.minio_prefix}/discovery/{operation}/{distrito}/{scrape_date}.jsonl"
                )
            minio_client.fput_object(
                bucket_name=config.minio_bucket,
                object_name=minio_object,
                file_path=local_path,
                content_type="application/x-ndjson",
                metadata={
                    "x-amz-meta-source": config.source_name,
                    "x-amz-meta-operation": operation,
                    "x-amz-meta-distrito": distrito,
                    "x-amz-meta-concelho": concelho or "",
                    "x-amz-meta-scrape-date": scrape_date,
                    "x-amz-meta-listing-count": str(len(all_items)),
                },
            )

            log.info(
                "[%s] %s/%s: discovery done — %d listings → s3://%s/%s",
                config.source_name,
                operation,
                segment_label,
                len(all_items),
                config.minio_bucket,
                minio_object,
            )
            return {
                "operation": operation,
                "distrito": distrito,
                "concelho": concelho,
                "discovery_minio_path": minio_object,
                "listing_count": len(all_items),
                "scrape_date": scrape_date,
                "force_full": segment.get("force_full", False),
                "temp_dir": tmp_dir,
            }

        @task()
        def crawl_details(discovery_result: dict) -> dict:
            """
            Phase 2: Fetch property detail for discovered listings.

            Incremental logic:
            - Query bronze for property_ids scraped within detail_refresh_days
            - Only fetch detail for NEW listings not in that set
            - Carry forward previous detail data from MinIO for skipped listings
            - Force full refresh overrides this and fetches everything
            """
            import requests
            from airflow.models import Variable
            from minio import Minio
            from tenacity import (
                retry,
                retry_if_exception_type,
                stop_after_attempt,
                wait_exponential,
            )

            @retry(
                stop=stop_after_attempt(config.max_retries),
                wait=wait_exponential(
                    multiplier=1, min=config.retry_backoff_seconds, max=60
                ),
                retry=retry_if_exception_type(
                    (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.HTTPError,
                    )
                ),
                reraise=True,
            )
            def _fetch_detail(url, params, timeout):
                resp = requests.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp

            api_key = Variable.get("ZENROWS_API_KEY")
            operation = discovery_result["operation"]
            distrito = discovery_result["distrito"]
            concelho = discovery_result.get("concelho")
            scrape_date = discovery_result["scrape_date"]
            discovery_path = discovery_result["discovery_minio_path"]
            force_full = discovery_result.get("force_full", False)
            segment_label = f"{distrito}/{concelho}" if concelho else distrito

            minio_client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            # Read discovery JSONL from MinIO
            resp = minio_client.get_object(config.minio_bucket, discovery_path)
            try:
                raw_bytes = resp.read()
            finally:
                resp.close()
                resp.release_conn()

            discovery_items = [
                json.loads(line)
                for line in raw_bytes.decode("utf-8").split("\n")
                if line.strip()
            ]
            # Deduplicate: discovery pagination can return the same listing
            # on multiple pages. Use dict.fromkeys to preserve first occurrence order.
            items_without_id = sum(1 for item in discovery_items if not item.get("property_id"))
            if items_without_id:
                log.warning(
                    "[%s] %s/%s: %d discovery items missing property_id — skipped",
                    config.source_name, operation, segment_label, items_without_id,
                )
            all_ids = list(dict.fromkeys(
                str(item["property_id"])
                for item in discovery_items
                if item.get("property_id")
            ))

            # Determine which IDs need fetching
            if force_full:
                ids_to_fetch = all_ids
                ids_to_skip = set()
                previous_details = {}
                log.info(
                    "[%s] %s/%s: force full — fetching all %d listings",
                    config.source_name,
                    operation,
                    segment_label,
                    len(ids_to_fetch),
                )
            else:
                known_ids = _get_known_property_ids(config, config.detail_refresh_days)
                ids_to_fetch = [pid for pid in all_ids if pid not in known_ids]
                ids_to_skip = {pid for pid in all_ids if pid in known_ids}

                if ids_to_skip:
                    previous_details = _find_previous_detail(
                        config, minio_client, config.minio_bucket,
                        config.minio_prefix, operation, distrito,
                        concelho=concelho, exclude_date=scrape_date,
                    )
                else:
                    previous_details = {}

                log.info(
                    "[%s] %s/%s: %d total, %d new to fetch, "
                    "%d skipped (in bronze last %d days), %d previous details loaded",
                    config.source_name,
                    operation,
                    segment_label,
                    len(all_ids),
                    len(ids_to_fetch),
                    len(ids_to_skip),
                    config.detail_refresh_days,
                    len(previous_details),
                )

            # Fetch detail for new listings
            tmp_dir = tempfile.mkdtemp(prefix="idealista_det_")
            local_path = os.path.join(
                tmp_dir, f"{distrito}_{concelho or 'all'}_{operation}_{scrape_date}_detail.jsonl"
            )
            detail_count = 0
            carried_forward = 0
            errors = 0

            with open(local_path, "w", encoding="utf-8") as f:
                # Write carried-forward details first
                ids_to_refetch = []
                for pid in ids_to_skip:
                    if pid in previous_details:
                        prev = dict(previous_details[pid])  # copy to avoid mutating original
                        prev["_scrape_date"] = scrape_date
                        prev["_carried_forward"] = True
                        f.write(_jsonl_line(prev) + "\n")
                        carried_forward += 1
                    else:
                        # Missing from previous detail file (e.g. distrito→concelho transition)
                        # Re-fetch from API instead of silently dropping
                        ids_to_refetch.append(pid)

                if ids_to_refetch:
                    log.info(
                        "[%s] %s/%s: %d listings in bronze but missing from "
                        "previous detail file — will re-fetch from API",
                        config.source_name,
                        operation,
                        segment_label,
                        len(ids_to_refetch),
                    )
                    ids_to_fetch = ids_to_refetch + ids_to_fetch

                # Fetch new details from ZenRows
                for prop_id in ids_to_fetch:
                    url = config.detail_url.format(property_id=prop_id)
                    try:
                        detail_resp = _fetch_detail(
                            url,
                            {"apikey": api_key, "tld": ".pt"},
                            config.request_timeout_seconds,
                        )
                        detail = detail_resp.json()
                        detail["_property_id"] = prop_id
                        detail["_distrito"] = distrito
                        detail["_concelho"] = concelho or ""
                        detail["_operation"] = operation
                        detail["_scrape_date"] = scrape_date
                        detail["_carried_forward"] = False
                        f.write(_jsonl_line(detail) + "\n")
                        detail_count += 1
                    except Exception as exc:
                        log.warning(
                            "[%s] %s/%s: detail fetch failed for %s — %s",
                            config.source_name,
                            operation,
                            segment_label,
                            prop_id,
                            exc,
                        )
                        errors += 1
                    time.sleep(config.detail_rate_limit_seconds)

            # Upload detail JSONL to MinIO
            if concelho:
                minio_object = (
                    f"{config.minio_prefix}/detail/{operation}/{distrito}/{concelho}/{scrape_date}.jsonl"
                )
            else:
                minio_object = (
                    f"{config.minio_prefix}/detail/{operation}/{distrito}/{scrape_date}.jsonl"
                )
            minio_client.fput_object(
                bucket_name=config.minio_bucket,
                object_name=minio_object,
                file_path=local_path,
                content_type="application/x-ndjson",
                metadata={
                    "x-amz-meta-source": config.source_name,
                    "x-amz-meta-operation": operation,
                    "x-amz-meta-distrito": distrito,
                    "x-amz-meta-concelho": concelho or "",
                    "x-amz-meta-scrape-date": scrape_date,
                    "x-amz-meta-detail-fetched": str(detail_count),
                    "x-amz-meta-detail-carried-forward": str(carried_forward),
                    "x-amz-meta-errors": str(errors),
                },
            )

            log.info(
                "[%s] %s/%s: detail done — %d fetched, %d carried forward, "
                "%d errors → s3://%s/%s",
                config.source_name,
                operation,
                segment_label,
                detail_count,
                carried_forward,
                errors,
                config.minio_bucket,
                minio_object,
            )
            return {
                "operation": operation,
                "distrito": distrito,
                "concelho": concelho,
                "detail_minio_path": minio_object,
                "detail_count": detail_count,
                "carried_forward": carried_forward,
                "errors": errors,
                "scrape_date": scrape_date,
                "temp_dir": tmp_dir,
            }

        @task(trigger_rule="all_done")
        def cleanup_temp(
            discovery_results: list[dict], detail_results: list[dict]
        ):
            """Remove temp directories after all crawls complete."""
            seen: set[str] = set()
            for result in list(discovery_results) + list(detail_results):
                tmp = result.get("temp_dir")
                if tmp and tmp not in seen and Path(tmp).exists():
                    shutil.rmtree(tmp)
                    seen.add(tmp)
            log.info(
                "[%s] Cleaned up %d temp directories",
                config.source_name,
                len(seen),
            )

        @task(trigger_rule="all_done")
        def log_run_summary(detail_results: list[dict]) -> dict:
            """Log a structured summary of the entire ingestion run."""
            total_fetched = sum(r.get("detail_count", 0) for r in detail_results)
            total_carried = sum(r.get("carried_forward", 0) for r in detail_results)
            total_errors = sum(r.get("errors", 0) for r in detail_results)
            log.info("=" * 60)
            log.info("%s INGESTION COMPLETE", config.source_name.upper())
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
        api_check = check_api_availability()
        segments = build_segments(api_check)
        discovery_results = crawl_discovery.expand(segment=segments)
        detail_results = crawl_details.expand(discovery_result=discovery_results)
        cleanup_temp(discovery_results, detail_results)
        summary = log_run_summary(detail_results)

        if config.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_downstream = TriggerDagRunOperator(
                task_id="trigger_downstream",
                trigger_dag_id=config.trigger_dag_id,
                wait_for_completion=True,
                reset_dag_run=True,
            )
            summary >> trigger_downstream

    return idealista_ingestion()


dag = _create_dag()
