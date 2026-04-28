"""
API Ingestion Template — Flow A

Factory that creates Airflow DAGs for REST API ingestion.
Pipeline scope: availability check → fetch → upload raw JSON to MinIO (bronze).

Intentionally stops at raw JSON in MinIO. Transformation to Parquet/silver
is handled in a separate pipeline once the data has been explored and the
schema is confirmed.

Reusable across: INE, Eurostat, BPStat, ECB, Idealista, and any future API source.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class APIIndicator:
    """
    One API indicator/endpoint to fetch.

    Each indicator maps to a single API call. The endpoint_params dict
    is merged with the config's default_params to build the request URL.
    """

    code: str                           # Unique identifier (e.g. "0009201")
    name: str                           # Snake_case name for paths/logs
    description: str                    # Human-readable description
    category: str                       # Grouping tag (e.g. "housing")
    endpoint_params: dict[str, str] = field(default_factory=dict)
    storage_key: Optional[str] = None   # Override code for MinIO path (for paginated indicators)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Airflow XCom (JSON-safe)."""
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "endpoint_params": self.endpoint_params,
            "storage_key": self.storage_key,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> APIIndicator:
        """Reconstruct from XCom dict."""
        return cls(**d)


@dataclass
class APIIngestionConfig:
    """
    All parameters needed to instantiate a REST API ingestion DAG.

    --- API connection ---
    base_url + api_path form the endpoint.  default_params are sent
    with every request.  Each indicator adds its own endpoint_params.

    --- Indicator code parameter ---
    code_param_name controls how the indicator code is passed to the API:
        "varcd"        → ?varcd=0009201  (INE)
        "datasetcode"  → ?datasetcode=PRC_HPI_Q  (Eurostat)
    Set to None if the code is embedded in api_path instead.
    """

    # --- DAG identity ---
    dag_id: str
    source_name: str        # Short identifier: "ine", "eurostat", "bpstat"
    description: str

    # --- API connection ---
    base_url: str           # e.g. "https://www.ine.pt"
    api_path: str           # e.g. "/ine/json_indicador/pindica.jsp"
    default_params: dict[str, str] = field(default_factory=dict)
    code_param_name: Optional[str] = "varcd"  # Query param for indicator code
    code_in_path: bool = False  # Append code to URL path instead of query param

    request_timeout_seconds: int = 60
    max_retries: int = 3
    retry_backoff_seconds: int = 5
    rate_limit_delay_seconds: float = 1.0
    extra_headers: dict[str, str] = field(default_factory=dict)  # Custom HTTP headers (e.g. Supabase apikey)

    # --- Indicators (catalog) ---
    indicators: list[APIIndicator] = field(default_factory=list)

    # --- MinIO storage ---
    minio_bucket: str = "raw"
    minio_prefix: str = ""  # e.g. "ine" → raw/ine/{code}/...

    # --- Scheduling ---
    schedule: Optional[str] = None
    start_date: Optional[datetime] = None

    # --- DAG-level Airflow Params ---
    dag_params: dict = field(default_factory=dict)

    # --- Orchestration ---
    trigger_dag_id: Optional[str | list[str]] = None  # Auto-trigger DAG(s) after ingestion

    # --- DAG settings ---
    tags: list[str] = field(default_factory=list)
    retries: int = 2
    retry_delay_minutes: int = 5
    email_on_failure: bool = False


# ---------------------------------------------------------------------------
# DAG factory
# ---------------------------------------------------------------------------


def create_api_ingestion_dag(config: APIIngestionConfig):
    """
    Returns an Airflow DAG configured for the given APIIngestionConfig.

    Task graph (dynamic task mapping — one instance per indicator):

        check_api_availability
                │
        fetch_indicator  ←── .expand() over all indicators
                │
        upload_to_minio
              ╱   ╲
        cleanup   log_run_metadata
    """
    import pendulum
    from airflow.decorators import dag, task
    from airflow.models.param import Param

    resolved_start_date = config.start_date or pendulum.yesterday("UTC")

    if config.schedule is not None and config.start_date is None:
        raise ValueError(
            f"[{config.dag_id}] start_date must be set explicitly for scheduled DAGs "
            f"(schedule='{config.schedule}'). It controls backfill behaviour."
        )

    default_args = {
        "owner": "data-engineering",
        "retries": config.retries,
        "retry_delay": timedelta(minutes=config.retry_delay_minutes),
        "email_on_failure": config.email_on_failure,
    }

    airflow_params = {
        key: Param(
            default=spec.get("default", ""),
            description=spec.get("description", ""),
            type="string",
        )
        for key, spec in config.dag_params.items()
    }

    @dag(
        dag_id=config.dag_id,
        description=config.description,
        schedule=config.schedule,
        start_date=resolved_start_date,
        catchup=False,
        default_args=default_args,
        params=airflow_params,
        tags=["ingestion", "api", "minio"] + config.tags,
    )
    def api_ingestion_dag():

        # ------------------------------------------------------------------
        # Task 1: Check API availability
        # ------------------------------------------------------------------

        @task()
        def check_api_availability() -> dict:
            """
            Verifies the API endpoint is reachable before fetching indicators.

            Sends a lightweight request with the first indicator's params
            to confirm the API is responding. Fails the DAG early if the
            API is down.
            """
            import requests

            # Build a minimal test request using the first indicator
            test_params = {**config.default_params}
            if config.code_in_path and config.indicators:
                url = f"{config.base_url}{config.api_path}{config.indicators[0].code}"
            else:
                url = f"{config.base_url}{config.api_path}"
                if config.indicators and config.code_param_name:
                    test_params[config.code_param_name] = config.indicators[0].code

            log.info(
                "[%s] Checking API availability: %s (params=%s)",
                config.source_name, url, test_params,
            )

            resp = requests.get(
                url, params=test_params,
                headers=config.extra_headers or None,
                timeout=config.request_timeout_seconds,
            )
            resp.raise_for_status()

            info = {
                "url": url,
                "http_status": resp.status_code,
                "content_type": resp.headers.get("content-type", "unknown"),
                "indicator_count": len(config.indicators),
            }
            log.info("[%s] API available: %s", config.source_name, info)
            return info

        # ------------------------------------------------------------------
        # Task 2: Fetch a single indicator (mapped dynamically)
        # ------------------------------------------------------------------

        @task()
        def fetch_indicator(indicator_dict: dict) -> dict:
            """
            Fetches raw JSON for a single indicator from the API.

            Uses tenacity for retry with exponential backoff on transient
            failures (HTTP 5xx, connection errors).

            Saves raw JSON to a temp file for downstream tasks.
            """
            import requests
            from tenacity import (
                retry,
                retry_if_exception_type,
                stop_after_attempt,
                wait_exponential,
            )

            indicator = APIIndicator.from_dict(indicator_dict)

            params = {**config.default_params}
            if config.code_param_name:
                params[config.code_param_name] = indicator.code
            params.update(indicator.endpoint_params)

            if config.code_in_path:
                url = f"{config.base_url}{config.api_path}{indicator.code}"
            else:
                url = f"{config.base_url}{config.api_path}"

            log.info(
                "[%s] Fetching indicator %s (%s)",
                config.source_name, indicator.code, indicator.name,
            )

            @retry(
                stop=stop_after_attempt(config.max_retries),
                wait=wait_exponential(
                    multiplier=1,
                    min=config.retry_backoff_seconds,
                    max=60,
                ),
                retry=retry_if_exception_type(
                    (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                ),
                reraise=True,
            )
            def _do_fetch():
                resp = requests.get(
                    url, params=params,
                    headers=config.extra_headers or None,
                    timeout=config.request_timeout_seconds,
                )
                resp.raise_for_status()
                return resp.json()

            raw_data = _do_fetch()

            # Rate limiting: pause between requests
            time.sleep(config.rate_limit_delay_seconds)

            # Save raw JSON to temp file
            temp_dir = Path(tempfile.mkdtemp(prefix=f"api_{config.source_name}_"))
            safe_code = indicator.code.replace("/", "_")
            raw_path = temp_dir / f"{safe_code}.json"
            raw_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2))

            result = {
                "indicator": indicator_dict,
                "raw_json_path": str(raw_path),
                "temp_dir": str(temp_dir),
            }

            log.info(
                "[%s] Fetched %s → %s",
                config.source_name, indicator.code, raw_path,
            )
            return result

        # ------------------------------------------------------------------
        # Task 3: Upload raw JSON to MinIO (bronze)
        # ------------------------------------------------------------------

        @task()
        def upload_to_minio(fetch_result: dict) -> dict:
            """
            Uploads raw JSON to MinIO as bronze layer.

            Path:  s3://{bucket}/{prefix}/{code}/{timestamp}.json
            """
            from minio import Minio
            from airflow.models import Variable

            indicator_dict = fetch_result["indicator"]
            indicator = APIIndicator.from_dict(indicator_dict)
            ingest_ts = datetime.utcnow()
            timestamp = ingest_ts.strftime("%Y%m%dT%H%M%SZ")

            endpoint = Variable.get("MINIO_ENDPOINT", default_var="localhost:9000")
            access_key = Variable.get("MINIO_ACCESS_KEY")
            secret_key = Variable.get("MINIO_SECRET_KEY")
            client = Minio(
                endpoint, access_key=access_key,
                secret_key=secret_key, secure=False,
            )

            bucket = config.minio_bucket
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                log.info("[%s] Created MinIO bucket: %s", config.source_name, bucket)

            prefix = config.minio_prefix
            code = indicator.code

            # Bronze: raw JSON with timestamp
            path_key = indicator.storage_key or code
            raw_object = f"{prefix}/{path_key}/{timestamp}.json"
            client.fput_object(
                bucket_name=bucket,
                object_name=raw_object,
                file_path=fetch_result["raw_json_path"],
                metadata={
                    "x-amz-meta-source": config.source_name,
                    "x-amz-meta-indicator": code,
                    "x-amz-meta-indicator-name": indicator.name,
                    "x-amz-meta-category": indicator.category,
                    "x-amz-meta-ingested-at": ingest_ts.isoformat(),
                },
            )
            raw_uri = f"s3://{bucket}/{raw_object}"

            log.info(
                "[%s] Uploaded %s → %s",
                config.source_name, code, raw_uri,
            )

            return {
                "indicator_code": code,
                "indicator_name": indicator.name,
                "category": indicator.category,
                "raw_uri": raw_uri,
                "ingested_at": ingest_ts.isoformat(),
            }

        # ------------------------------------------------------------------
        # Task 4a: Cleanup temp directories
        # ------------------------------------------------------------------

        @task(trigger_rule="all_done")
        def cleanup_temp(fetch_results: list[dict], upload_results: list[dict]):
            """Removes temp directories after all uploads complete.
            Depends on upload_results to ensure cleanup only runs after uploads."""
            seen: set[str] = set()
            for result in fetch_results:
                temp_dir = result.get("temp_dir")
                if temp_dir and temp_dir not in seen and Path(temp_dir).exists():
                    shutil.rmtree(temp_dir)
                    seen.add(temp_dir)
            log.info(
                "[%s] Cleaned up %d temp directories",
                config.source_name, len(seen),
            )

        # ------------------------------------------------------------------
        # Task 4b: Log run metadata
        # ------------------------------------------------------------------

        @task(trigger_rule="all_done")
        def log_run_metadata(upload_results: list[dict]):
            """Logs a structured summary of the entire ingestion run."""
            log.info("=" * 60)
            log.info("API INGESTION COMPLETE — %s", config.source_name.upper())
            log.info("=" * 60)
            log.info("  Total indicators : %d", len(upload_results))
            log.info("")
            for r in upload_results:
                log.info("  [%s] %s", r["indicator_code"], r["indicator_name"])
                log.info("    Category : %s", r["category"])
                log.info("    Bronze   : %s", r["raw_uri"])
            log.info("=" * 60)

        # ------------------------------------------------------------------
        # Wire the task graph
        # ------------------------------------------------------------------

        # Serialize indicators for XCom
        indicator_dicts = [ind.to_dict() for ind in config.indicators]

        api_check = check_api_availability()

        # Dynamic task mapping: one task instance per indicator
        fetch_results = fetch_indicator.expand(indicator_dict=indicator_dicts)
        fetch_results.set_upstream(api_check)

        upload_results = upload_to_minio.expand(fetch_result=fetch_results)

        cleanup_temp(fetch_results, upload_results)
        metadata = log_run_metadata(upload_results)

        if config.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            dag_ids = (
                config.trigger_dag_id
                if isinstance(config.trigger_dag_id, list)
                else [config.trigger_dag_id]
            )
            prev = metadata
            for dag_id in dag_ids:
                trigger = TriggerDagRunOperator(
                    task_id=f"trigger_{dag_id}",
                    trigger_dag_id=dag_id,
                    wait_for_completion=True,
                    reset_dag_run=True,
                )
                prev >> trigger
                prev = trigger

    return api_ingestion_dag()
