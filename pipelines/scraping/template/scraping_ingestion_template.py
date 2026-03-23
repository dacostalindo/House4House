"""
Web Scraping Ingestion Template — Flow S

Factory that creates Airflow DAGs for web scraping ingestion.
Pipeline scope: site check → scrape regions → upload raw JSONL to MinIO (bronze).

Supports two scraping backends:
  - "requests": requests + BeautifulSoup for simple sites (no anti-bot protection)
  - "nodriver": undetected Chrome for sites with Cloudflare Turnstile / JS challenges

Reusable across: SCE energy certificates, and any future scraping source.
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScrapingRegion:
    """
    One geographic region to scrape.

    Each region maps to a separate scraping task. The params dict
    is passed to the scrape_fn for constructing queries.
    """

    code: str           # Unique ID for MinIO paths (e.g. "11_06")
    name: str           # Human label (e.g. "Lisboa")
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Airflow XCom (JSON-safe)."""
        return {"code": self.code, "name": self.name, "params": self.params}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScrapingRegion:
        """Reconstruct from XCom dict."""
        return cls(**d)


@dataclass
class ScrapingIngestionConfig:
    """
    All parameters needed to instantiate a web scraping ingestion DAG.

    --- Backend ---
    backend controls how the scraper interacts with the target site:
        "requests"  → requests.Session + BeautifulSoup (simple sites)
        "nodriver"  → undetected Chrome via nodriver (Turnstile/JS sites)

    --- scrape_fn contract ---
    For requests backend:
        def scrape_fn(session: requests.Session, region: ScrapingRegion, config) -> list[dict]
    For nodriver backend:
        async def scrape_fn(page, region: ScrapingRegion, config) -> list[dict]
    """

    # --- DAG identity ---
    dag_id: str
    source_name: str
    description: str

    # --- Target site ---
    target_url: str         # POST/scrape endpoint
    landing_url: str        # GET first (cookies / Turnstile)

    # --- Scraping ---
    regions: list[ScrapingRegion] = field(default_factory=list)
    scrape_fn: Optional[Callable] = None
    backend: str = "requests"       # "requests" or "nodriver"
    headless: bool = True           # nodriver: headless mode
    browser_executable_path: Optional[str] = None  # nodriver: Chrome path
    turnstile_wait_seconds: int = 15

    # --- Rate limiting ---
    request_delay: float = 3.0
    request_timeout: int = 30
    max_retries: int = 3
    browser_restart_interval: int = 100  # restart browser every N pages

    # --- Session ---
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    accept_language: str = "pt-PT,pt;q=0.9,en;q=0.8"
    extra_headers: dict[str, str] = field(default_factory=dict)

    # --- MinIO storage ---
    minio_bucket: str = "raw"
    minio_prefix: str = ""  # e.g. "sce_pce" → raw/sce_pce/{region}/...

    # --- Scheduling ---
    schedule: Optional[str] = None
    start_date: Optional[datetime] = None

    # --- Orchestration ---
    trigger_dag_id: Optional[str] = None

    # --- DAG settings ---
    tags: list[str] = field(default_factory=list)
    retries: int = 2
    retry_delay_minutes: int = 5
    email_on_failure: bool = False


# ---------------------------------------------------------------------------
# DAG factory
# ---------------------------------------------------------------------------


def create_scraping_ingestion_dag(config: ScrapingIngestionConfig):
    """
    Returns an Airflow DAG configured for the given ScrapingIngestionConfig.

    Task graph (dynamic task mapping — one instance per region):

        check_site_availability
                │
        scrape_region  ←── .expand() over all regions
                │
        upload_to_minio
              ╱   ╲
        cleanup   log_run_metadata
                        │
                trigger_downstream (optional)
    """
    import pendulum
    from airflow.decorators import dag, task

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

    @dag(
        dag_id=config.dag_id,
        description=config.description,
        schedule=config.schedule,
        start_date=resolved_start_date,
        catchup=False,
        default_args=default_args,
        tags=["ingestion", "scraping", "minio"] + config.tags,
    )
    def scraping_ingestion_dag():

        # ------------------------------------------------------------------
        # Task 1: Check site availability
        # ------------------------------------------------------------------

        @task()
        def check_site_availability() -> dict:
            """Verify the target site is reachable before scraping."""
            import requests as req

            log.info("[%s] Checking site: %s", config.source_name, config.landing_url)

            resp = req.get(
                config.landing_url,
                timeout=config.request_timeout,
                headers={"User-Agent": config.user_agent},
            )
            resp.raise_for_status()

            info = {
                "url": config.landing_url,
                "http_status": resp.status_code,
                "content_length": len(resp.content),
                "region_count": len(config.regions),
            }
            log.info("[%s] Site available: %s", config.source_name, info)
            return info

        # ------------------------------------------------------------------
        # Task 2: Scrape a single region (mapped dynamically)
        # ------------------------------------------------------------------

        @task(execution_timeout=timedelta(hours=4), max_active_tis_per_dag=4)
        def scrape_region(region_dict: dict) -> dict:
            """
            Scrape all data for a single region.

            Creates the appropriate session/browser, calls scrape_fn,
            and saves results as JSONL to a temp file.
            """
            region = ScrapingRegion.from_dict(region_dict)
            log.info("[%s] Scraping region: %s (%s)", config.source_name, region.name, region.code)

            if config.backend == "nodriver":
                records = _scrape_with_nodriver(region, config)
            else:
                records = _scrape_with_requests(region, config)

            log.info("[%s] %s: %d records scraped", config.source_name, region.name, len(records))

            # Save as JSONL to temp file
            temp_dir = Path(tempfile.mkdtemp(prefix=f"scrape_{config.source_name}_"))
            jsonl_path = temp_dir / f"{region.code}.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            return {
                "region": region_dict,
                "jsonl_path": str(jsonl_path),
                "temp_dir": str(temp_dir),
                "record_count": len(records),
            }

        # ------------------------------------------------------------------
        # Task 3: Upload JSONL to MinIO
        # ------------------------------------------------------------------

        @task()
        def upload_to_minio(scrape_result: dict) -> dict:
            """Upload JSONL to MinIO as bronze layer."""
            from minio import Minio
            from airflow.models import Variable

            region = ScrapingRegion.from_dict(scrape_result["region"])
            ingest_ts = datetime.utcnow()
            timestamp = ingest_ts.strftime("%Y%m%dT%H%M%SZ")
            scrape_date = ingest_ts.strftime("%Y%m%d")

            client = Minio(
                Variable.get("MINIO_ENDPOINT"),
                access_key=Variable.get("MINIO_ACCESS_KEY"),
                secret_key=Variable.get("MINIO_SECRET_KEY"),
                secure=False,
            )

            bucket = config.minio_bucket
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)

            object_name = f"{config.minio_prefix}/{region.code}/{scrape_date}/{timestamp}.jsonl"
            client.fput_object(
                bucket_name=bucket,
                object_name=object_name,
                file_path=scrape_result["jsonl_path"],
                metadata={
                    "x-amz-meta-source": config.source_name,
                    "x-amz-meta-region": region.code,
                    "x-amz-meta-region-name": region.name,
                    "x-amz-meta-record-count": str(scrape_result["record_count"]),
                    "x-amz-meta-ingested-at": ingest_ts.isoformat(),
                },
            )
            uri = f"s3://{bucket}/{object_name}"
            log.info("[%s] Uploaded %s → %s", config.source_name, region.name, uri)

            return {
                "region_code": region.code,
                "region_name": region.name,
                "record_count": scrape_result["record_count"],
                "minio_uri": uri,
                "ingested_at": ingest_ts.isoformat(),
            }

        # ------------------------------------------------------------------
        # Task 4a: Cleanup temp directories
        # ------------------------------------------------------------------

        @task(trigger_rule="all_done")
        def cleanup_temp(scrape_results: list[dict], upload_results: list[dict]):
            """Remove temp directories after all uploads complete."""
            seen: set[str] = set()
            for result in scrape_results:
                temp_dir = result.get("temp_dir")
                if temp_dir and temp_dir not in seen and Path(temp_dir).exists():
                    shutil.rmtree(temp_dir)
                    seen.add(temp_dir)
            log.info("[%s] Cleaned up %d temp directories", config.source_name, len(seen))

        # ------------------------------------------------------------------
        # Task 4b: Log run metadata
        # ------------------------------------------------------------------

        @task(trigger_rule="all_done")
        def log_run_metadata(upload_results: list[dict]):
            """Log a structured summary of the scraping run."""
            log.info("=" * 60)
            log.info("SCRAPING COMPLETE — %s", config.source_name.upper())
            log.info("=" * 60)
            total_records = sum(r.get("record_count", 0) for r in upload_results)
            log.info("  Total records : %d", total_records)
            log.info("  Regions       : %d", len(upload_results))
            for r in upload_results:
                log.info("  [%s] %s: %d records → %s",
                         r["region_code"], r["region_name"],
                         r["record_count"], r["minio_uri"])
            log.info("=" * 60)

        # ------------------------------------------------------------------
        # Wire the task graph
        # ------------------------------------------------------------------

        region_dicts = [r.to_dict() for r in config.regions]

        site_check = check_site_availability()
        scrape_results = scrape_region.expand(region_dict=region_dicts)
        scrape_results.set_upstream(site_check)

        upload_results = upload_to_minio.expand(scrape_result=scrape_results)

        cleanup_temp(scrape_results, upload_results)
        metadata = log_run_metadata(upload_results)

        if config.trigger_dag_id:
            from airflow.operators.trigger_dagrun import TriggerDagRunOperator

            trigger_downstream = TriggerDagRunOperator(
                task_id="trigger_downstream",
                trigger_dag_id=config.trigger_dag_id,
                wait_for_completion=True,
                reset_dag_run=True,
            )
            metadata >> trigger_downstream

    return scraping_ingestion_dag()


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------


def _scrape_with_requests(region: ScrapingRegion, config: ScrapingIngestionConfig) -> list[dict]:
    """Scrape using requests + BeautifulSoup."""
    import requests as req

    session = req.Session()
    session.headers.update({
        "User-Agent": config.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": config.accept_language,
        "Referer": config.landing_url,
        "Origin": config.landing_url.rsplit("/", 1)[0],
    })
    session.headers.update(config.extra_headers)

    # Hit landing page for cookies
    session.get(config.landing_url, timeout=config.request_timeout)

    return config.scrape_fn(session, region, config)


def _ensure_display():
    """Start Xvfb virtual display if no DISPLAY is set (Docker container)."""
    import os
    import subprocess

    if os.environ.get("DISPLAY"):
        return  # Already have a display

    # Pick a display number based on PID to avoid collisions
    display_num = 10 + (os.getpid() % 90)
    display = f":{display_num}"

    try:
        subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = display
        log.info("Started Xvfb on %s", display)
    except FileNotFoundError:
        log.warning("Xvfb not found — falling back to headless mode")


def _scrape_with_nodriver(region: ScrapingRegion, config: ScrapingIngestionConfig) -> list[dict]:
    """Scrape using nodriver (undetected Chrome)."""
    import asyncio

    # If running in headed mode (for Turnstile), ensure a virtual display exists
    if not config.headless:
        _ensure_display()

    async def _run():
        import nodriver as uc

        kwargs = {
            "headless": config.headless,
            "sandbox": False,
            "browser_args": ["--disable-dev-shm-usage", "--disable-gpu"],
        }
        if config.browser_executable_path:
            kwargs["browser_executable_path"] = config.browser_executable_path

        # Retry browser launch — nodriver's internal timeout (2.75s) is too
        # short when the container is under load with multiple Chrome instances.
        browser = None
        for attempt in range(3):
            try:
                browser = await uc.start(**kwargs)
                break
            except Exception:
                if attempt == 2:
                    raise
                log.warning("[%s] Browser launch attempt %d failed, retrying...",
                            config.source_name, attempt + 1)
                await asyncio.sleep(3 * (attempt + 1))

        try:
            page = await browser.get(config.landing_url)
            # Wait for Turnstile to auto-solve
            wait_secs = config.turnstile_wait_seconds or 10
            log.info("[%s] Waiting %ds for Turnstile...", config.source_name, wait_secs)
            await asyncio.sleep(wait_secs)
            return await config.scrape_fn(page, region, config)
        finally:
            browser.stop()

    # nodriver is async — run in a new event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(_run())).result()
        else:
            return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())
