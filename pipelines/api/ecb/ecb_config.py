"""
ECB — Euribor Rate Ingestion Configuration

ECB Statistical Data Warehouse SDMX REST API:
  https://data-api.ecb.europa.eu/service/data/FM/{series_key}?format=jsondata

3 Euribor monthly rate series (3M, 6M, 12M) for mortgage affordability modelling.
"""

from __future__ import annotations

from datetime import datetime

from pipelines.api.template.api_ingestion_template import (
    APIIndicator,
    APIIngestionConfig,
)

ECB_INDICATORS = [
    APIIndicator(
        code="M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
        name="euribor_3m",
        description="Euribor 3-month rate (monthly average)",
        category="interest_rates",
    ),
    APIIndicator(
        code="M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA",
        name="euribor_6m",
        description="Euribor 6-month rate (monthly average)",
        category="interest_rates",
    ),
    APIIndicator(
        code="M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA",
        name="euribor_12m",
        description="Euribor 12-month rate (monthly average)",
        category="interest_rates",
    ),
]

# Series keys for bronze DAG (kept in sync with indicators above)
SERIES_KEYS = [ind.code for ind in ECB_INDICATORS]

ECB_CONFIG = APIIngestionConfig(
    dag_id="ecb_api_ingestion",
    source_name="ecb",
    description=(
        "ECB Euribor rates via SDMX REST API. "
        "Fetches 3M, 6M, and 12M monthly averages. "
        "Stores raw SDMX JSON in MinIO raw layer."
    ),
    base_url="https://data-api.ecb.europa.eu",
    api_path="/service/data/FM/",
    code_param_name=None,
    code_in_path=True,
    default_params={"format": "jsondata"},
    indicators=ECB_INDICATORS,
    minio_bucket="raw",
    minio_prefix="ecb",
    schedule="0 6 1 * *",
    start_date=datetime(2025, 1, 1),
    trigger_dag_id="ecb_bronze_load",
    tags=["ecb", "euribor", "interest_rates", "macro"],
)
