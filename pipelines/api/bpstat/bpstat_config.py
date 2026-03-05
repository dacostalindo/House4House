"""
BPStat — Banco de Portugal Ingestion Configuration

BPStat REST API (JSON-stat 2.0):
  https://bpstat.bportugal.pt/data/v1/domains/{domain_id}/datasets/{dataset_id}

3 domains, 16 datasets covering housing credit, interest rates, and housing prices.

Not included: Domain 18 (household debt, ~16.8K series, mostly corporate).
The housing-specific subset (16 series) can be added later if needed.
"""

from __future__ import annotations

from datetime import datetime

from pipelines.api.template.api_ingestion_template import (
    APIIndicator,
    APIIngestionConfig,
)

BPSTAT_INDICATORS = [
    # -----------------------------------------------------------------------
    # Domain 186 — Housing credit (4 datasets, 40 series)
    # -----------------------------------------------------------------------
    APIIndicator(
        code="186/datasets/d45bb68e792a6b1b2fc36d6a90da4f20",
        name="housing_credit_volumes",
        description="Loan volumes, repayment distributions, amortization",
        category="housing_credit",
    ),
    APIIndicator(
        code="186/datasets/6a83b46f5911d1b086a2891746a2fd9a",
        name="housing_credit_rates",
        description="Interest rates by type (fixed, floating, mixed)",
        category="housing_credit",
    ),
    APIIndicator(
        code="186/datasets/85c2d956038233432ce61f230f7dddab",
        name="housing_credit_fixed_rate_term",
        description="By initial fixed rate term",
        category="housing_credit",
    ),
    APIIndicator(
        code="186/datasets/63e8780cdb0c94c323528c7237b7a4b8",
        name="housing_credit_floating",
        description="Floating rate loan shares",
        category="housing_credit",
    ),

    # -----------------------------------------------------------------------
    # Domain 21 — Interest rates (10 datasets, 253 series)
    # -----------------------------------------------------------------------
    APIIndicator(
        code="21/datasets/07d36f662cea4b19f4b2c2cf5435771d",
        name="ir_credit_purpose_fixed_rate",
        description="Credit by purpose with initial fixed rate terms",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/0a8ba3498e4bdef200b80595dcc3fd8c",
        name="ir_credit_sectors",
        description="Credit metrics by institutional sectors",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/5e42e78146bb44759188678266b04c4e",
        name="ir_credit_purpose_metrics",
        description="Credit purpose with metrics across sectors",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/6eaa8db94523f54733dddc22479c11a4",
        name="ir_fixed_rate_counterparty",
        description="Fixed rate terms by counterparty/reference institutional data",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/851facff504532e95cf096ca9c6a8b9a",
        name="ir_original_maturity",
        description="Credit by original maturity and institutional sectors",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/9744c7a78f7417d4a91cf1a1b55fac1d",
        name="ir_step_values_flows",
        description="Credit step values with flows/stocks/prices",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/9ab0b6dd481ff9d0a79aeca89363b9ec",
        name="ir_step_values_fixed_rate",
        description="Step values with initial fixed rate terms across sectors",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/c4db40b75370917aaf045d1cff74c142",
        name="ir_credit_items",
        description="Credit metrics by source and items",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/ec7b2a0f066656833f1013b3a2f9f189",
        name="ir_maturity_counterparty",
        description="Credit by original maturity and counterparty sectors",
        category="interest_rates",
    ),
    APIIndicator(
        code="21/datasets/f648a7e7dec2e61dd4bdd6ba56ac519b",
        name="ir_maturity_sectors",
        description="Credit flows/stocks/prices by maturity and sectors",
        category="interest_rates",
    ),

    # -----------------------------------------------------------------------
    # Domain 39 — Housing prices (2 datasets, 18 series)
    # -----------------------------------------------------------------------
    APIIndicator(
        code="39/datasets/b8cc662879c9f7b0f3faf89c7871fc38",
        name="housing_price_indicators",
        description="Housing price statistics and indicators",
        category="housing_prices",
    ),
    APIIndicator(
        code="39/datasets/da133c091337a417b8b242c65e477ca0",
        name="housing_price_indices",
        description="Transaction price indices (new/existing dwellings)",
        category="housing_prices",
    ),
]

# Dataset IDs for bronze DAG (kept in sync with indicators above)
DATASET_CODES = [ind.code for ind in BPSTAT_INDICATORS]

BPSTAT_CONFIG = APIIngestionConfig(
    dag_id="bpstat_api_ingestion",
    source_name="bpstat",
    description=(
        "Banco de Portugal statistical data via BPStat REST API. "
        "Fetches housing credit, interest rates, and housing prices. "
        "Stores raw JSON-stat in MinIO raw layer."
    ),
    base_url="https://bpstat.bportugal.pt",
    api_path="/data/v1/domains/",
    code_in_path=True,
    code_param_name=None,
    default_params={"lang": "EN"},
    indicators=BPSTAT_INDICATORS,
    minio_bucket="raw",
    minio_prefix="bpstat",
    schedule="0 6 15 * *",
    start_date=datetime(2025, 1, 1),
    trigger_dag_id="bpstat_bronze_load",
    tags=["bpstat", "macro", "mortgage", "lending", "housing_prices"],
)
