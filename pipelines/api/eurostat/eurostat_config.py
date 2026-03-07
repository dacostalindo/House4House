"""Eurostat HPI — S18 configuration.

Single dataset: PRC_HPI_Q (House Price Index, quarterly, 2015=100).
All EU/EEA countries included for cross-country benchmarking.
"""

from __future__ import annotations

from datetime import datetime

from pipelines.api.template.api_ingestion_template import (
    APIIndicator,
    APIIngestionConfig,
)

# ---------------------------------------------------------------------------
# Indicators (single dataset)
# ---------------------------------------------------------------------------

EUROSTAT_INDICATORS = [
    APIIndicator(
        code="prc_hpi_q",
        name="house_price_index",
        description="House Price Index (2015=100) — quarterly, all EU countries",
        category="housing_prices",
    ),
]

# Convenience list for the bronze DAG
DATASET_CODES = [ind.code for ind in EUROSTAT_INDICATORS]

# ---------------------------------------------------------------------------
# DAG configuration
# ---------------------------------------------------------------------------

EUROSTAT_CONFIG = APIIngestionConfig(
    dag_id="eurostat_api_ingestion",
    source_name="eurostat",
    description="Eurostat House Price Index — quarterly HPI for EU countries",
    base_url="https://ec.europa.eu/eurostat",
    api_path="/api/dissemination/sdmx/2.1/data/",
    code_in_path=True,
    code_param_name=None,
    default_params={"format": "JSON", "lang": "EN"},
    request_timeout_seconds=120,
    rate_limit_delay_seconds=0,
    indicators=EUROSTAT_INDICATORS,
    minio_bucket="raw",
    minio_prefix="eurostat",
    schedule="0 6 5 1,4,7,10 *",
    start_date=datetime(2025, 1, 1),
    trigger_dag_id="eurostat_bronze_load",
    tags=["eurostat", "macro", "housing_prices", "hpi"],
)
