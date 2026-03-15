"""
INE (Statistics Portugal) — API Ingestion Configuration

Source:  https://www.ine.pt (public JSON API, no authentication required)
API:     https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd={code}&Dim1=T&lang=EN
Format:  JSON (raw, stored as-is in MinIO bronze layer)
Refresh: Quarterly (most housing indicators are quarterly; some monthly)

--- HOW TO TRIGGER ---

Trigger this DAG manually from the Airflow UI:
    Airflow UI → ine_api_ingestion → Trigger DAG

No config parameters needed — all indicator codes are defined below.

--- ADDING INDICATORS ---

Add a new APIIndicator entry to the INE_INDICATORS list below.
No template code changes needed — the pipeline handles the rest.

Indicator codes can be found at:
    1. Browse https://www.ine.pt → choose a dataset → inspect URL for varcd=XXXXXXX
    2. Search the metadata service: http://smi.ine.pt/Indicador
    3. API endpoint: https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd=XXXXXXX&Dim1=T&lang=EN

Dimension reference:
    Dim1 — Time period.  T = all periods; or e.g. "2023,2022" for specific years.
    Dim2 — Geography.    T = all; lvl@1 = national; lvl@2 = NUTS-II; lvl@3 = NUTS-III.
    Additional dimensions (Dim3, Dim4…) vary by indicator — check smi.ine.pt.
"""

from datetime import datetime

from pipelines.api.template.api_ingestion_template import (
    APIIndicator,
    APIIngestionConfig,
)


# ---------------------------------------------------------------------------
# Indicator catalog
# ---------------------------------------------------------------------------

INE_INDICATORS = [

    # ── Housing: prices ────────────────────────────────────────────────────
    APIIndicator(
        code="0009201",
        name="house_price_index",
        description="Housing price index (Base 2015) by Category of housing unit; Quarterly",
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0009207",
        name="commercial_property_price_index",
        description="Commercial property price index (Base 2015); Annual",
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012234",
        name="median_dwelling_sales_value_by_sector",
        description=(
            "Median value of dwellings sales in last 12 months (€/m²) "
            "by NUTS-2024 and Institutional sector of purchaser; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012235",
        name="median_flat_sales_value",
        description=(
            "Median value of dwelling sales in flats in last 12 months (€/m²) "
            "by NUTS-2024; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: transactions ──────────────────────────────────────────────
    APIIndicator(
        code="0012785",
        name="housing_transactions_count",
        description=(
            "Transactions (No.) of housing units by NUTS-2024, Category, "
            "Tax residence and Institutional sector of purchaser; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012786",
        name="housing_transactions_value",
        description=(
            "Transactions (€) of housing units by NUTS-2024, Category, "
            "Tax residence and Institutional sector of purchaser; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012787",
        name="housing_transactions_count_annual",
        description="Transactions (No.) of housing units by NUTS-2024; Annual",
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012788",
        name="housing_transactions_value_annual",
        description="Transactions (€) of housing units by NUTS-2024; Annual",
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: rental market ─────────────────────────────────────────────
    APIIndicator(
        code="0012571",
        name="median_rental_value_nuts",
        description=(
            "Median house rental value of new lease agreements (€/m²) "
            "by NUTS-2024; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012572",
        name="new_lease_agreements_count_nuts",
        description="New lease agreements of dwellings (No.) by NUTS-2024; Quarterly",
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012573",
        name="median_rental_value_cities",
        description=(
            "Median house rental value of new lease agreements (€/m²) "
            "by Municipalities >100k inhabitants; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012574",
        name="new_lease_agreements_count_cities",
        description=(
            "New lease agreements of dwellings (No.) by Municipalities "
            ">100k inhabitants; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: construction ──────────────────────────────────────────────
    APIIndicator(
        code="0012096",
        name="licensed_buildings",
        description=(
            "Licensed buildings (No.) by NUTS-2024, Type of project "
            "and Project purpose; Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012778",
        name="completed_dwellings_new_construction",
        description=(
            "Completed dwellings (No.) in new constructions for family housing "
            "by NUTS-2024; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0011750",
        name="housing_construction_cost_index",
        description=(
            "New housing construction cost index (YoY growth rate - Base 2021 %) "
            "by Production factor; Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: mortgage finance ──────────────────────────────────────────
    APIIndicator(
        code="0006340",
        name="housing_loan_interest_rate",
        description=(
            "Interest rate (%) on housing loans by regime, "
            "financing purpose and interest payer; Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0006341",
        name="housing_loan_outstanding_liability",
        description=(
            "Average outstanding liability (€) on housing loans "
            "by signing period, regime and purpose; Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008867",
        name="housing_loan_interest_rate_nuts",
        description=(
            "Interest rate (Série 2012 - %) on housing loans "
            "by Geographic localization (NUTS I); Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008870",
        name="housing_loan_total_interests_nuts",
        description=(
            "Total interests (Série 2012 - €) on housing loans "
            "by Geographic localization (NUTS I); Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: sales (updated methodology) ────────────────────────────────
    APIIndicator(
        code="0012236",
        name="median_dwelling_sales_value_per_m2",
        description=(
            "Median value of family housing sales in last 12 months (2022 methodology - €/m²) "
            "by NUTS-2024 and Institutional sector; Quarterly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: construction (additional) ────────────────────────────────
    APIIndicator(
        code="0012097",
        name="licensed_dwellings_new_construction",
        description=(
            "Licensed dwellings (No.) in new constructions for family housing "
            "by NUTS-2024 and Typology; Monthly"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008321",
        name="completed_dwellings_new_construction_annual",
        description=(
            "Completed dwellings (No.) in new constructions for family housing "
            "by NUTS and Typology; Annual"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Housing: building stock (Census 2021) ─────────────────────────────
    APIIndicator(
        code="0012575",
        name="building_aging_index",
        description=(
            "Building aging index (No.) by Geographic location "
            "at Census 2021; Decennial"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012581",
        name="buildings_needing_repair_pct",
        description=(
            "Proportion of buildings needing repair (%) "
            "by Geographic location at Census 2021; Decennial"
        ),
        category="housing",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Demographics ───────────────────────────────────────────────────────
    APIIndicator(
        code="0001271",
        name="old_age_dependency_ratio",
        description="Old-age dependency ratio (No.) by Sex; Annual",
        category="demographics",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008273",
        name="resident_population",
        description=(
            "Resident population (No.) by NUTS-2013, Sex and Age group; Annual"
        ),
        category="demographics",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008337",
        name="population_density",
        description=(
            "Population density (No./km²) by Place of residence; Annual"
        ),
        category="demographics",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Census 2021: employment (parish-level) ───────────────────────────
    APIIndicator(
        code="0012357",
        name="census_employment_rate",
        description=(
            "Employment rate (%) by Geographic location "
            "at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012328",
        name="census_unemployment_rate",
        description=(
            "Unemployment rate (%) by Geographic location "
            "at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012317",
        name="census_activity_rate",
        description=(
            "Activity rate (%) by Geographic location "
            "at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012341",
        name="census_employees_pct",
        description=(
            "Proportion of employees (%) by Geographic location "
            "at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Census 2021: education (parish-level) ────────────────────────────
    APIIndicator(
        code="0012316",
        name="census_higher_education_pct",
        description=(
            "Proportion of population with higher education (%) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012315",
        name="census_lower_secondary_pct",
        description=(
            "Proportion of population with at least lower secondary education (%) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012327",
        name="census_upper_secondary_pct",
        description=(
            "Proportion of population with at least upper secondary education (%) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012323",
        name="census_no_education_pct",
        description=(
            "Proportion of population with no education (%) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Census 2021: foreign population (parish-level) ───────────────────
    APIIndicator(
        code="0012314",
        name="census_foreign_nationality_pct",
        description=(
            "Proportion of resident population with foreign nationality (%) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012353",
        name="census_foreign_localization_quotient",
        description=(
            "Localization quotient of foreign-nationality residents (No.) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Census 2021: age & commuting (parish-level) ──────────────────────
    APIIndicator(
        code="0012374",
        name="census_mean_age",
        description=(
            "Mean age of resident population (Years) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012331",
        name="census_avg_commuting_time",
        description=(
            "Average commuting time (minutes) "
            "by Geographic location at Census 2021; Decennial (parish-level)"
        ),
        category="census_2021",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Employment: annual (municipality-level) ──────────────────────────
    APIIndicator(
        code="0012652",
        name="employees_by_education_level",
        description=(
            "Employees (No.) by Geographic location (NUTS-2013), "
            "Sex and Educational attainment level; Annual (municipality-level)"
        ),
        category="economy",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0012660",
        name="employees_higher_education_pct",
        description=(
            "Proportion of employees with higher education (%) "
            "by Geographic location (NUTS-2013); Annual (municipality-level)"
        ),
        category="economy",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Tourism ───────────────────────────────────────────────────────────
    APIIndicator(
        code="0009808",
        name="tourism_overnight_stays",
        description=(
            "Overnight stays (No.) in tourism accommodation establishments "
            "by NUTS-2013 and Accommodation type; Monthly"
        ),
        category="tourism",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Economy ───────────────────────────────────────────────────────────
    APIIndicator(
        code="0008351",
        name="consumer_price_index",
        description=(
            "Consumer price index (CPI, Base 2012) "
            "by NUTS-II and COICOP consumption class; Annual"
        ),
        category="economy",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0011190",
        name="gdp_per_capita_ppc",
        description=(
            "GDP per capita in PPC (EU27, Base 2016 - €) "
            "by NUTS-2013; Annual"
        ),
        category="economy",
        endpoint_params={"Dim1": "T"},
    ),

    # ── Innovation & technology ──────────────────────────────────────────
    APIIndicator(
        code="0008515",
        name="ict_companies_count",
        description=(
            "Enterprises with ICT activities (No.) "
            "by NUTS-2013 (CAE Rev. 3); Annual"
        ),
        category="innovation",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008519",
        name="ict_gross_value_added",
        description=(
            "Gross value added in ICT activities (€) "
            "by NUTS-2013 (CAE Rev. 3); Annual"
        ),
        category="innovation",
        endpoint_params={"Dim1": "T"},
    ),
    APIIndicator(
        code="0008521",
        name="high_tech_companies_count",
        description=(
            "High and medium-high technology industry enterprises (No.) "
            "by NUTS-2013 (CAE Rev. 3); Annual"
        ),
        category="innovation",
        endpoint_params={"Dim1": "T"},
    ),
]


# ---------------------------------------------------------------------------
# DAG configuration
# ---------------------------------------------------------------------------

INE_CONFIG = APIIngestionConfig(
    # --- DAG identity ---
    dag_id="ine_api_ingestion",
    source_name="ine",
    description=(
        "INE (Statistics Portugal) API ingestion. "
        "Fetches 33 indicators (housing, demographics, tourism, economy, innovation), "
        "stores raw JSON (bronze) in MinIO. No authentication required."
    ),

    # --- API connection ---
    base_url="https://www.ine.pt",
    api_path="/ine/json_indicador/pindica.jsp",
    default_params={"op": "2", "lang": "EN"},
    code_param_name="varcd",

    request_timeout_seconds=60,
    max_retries=3,
    retry_backoff_seconds=5,
    rate_limit_delay_seconds=1.0,

    # --- Indicators ---
    indicators=INE_INDICATORS,

    # --- MinIO ---
    minio_bucket="raw",
    minio_prefix="ine",

    # --- Schedule: monthly refresh (1st of each month at 06:00 UTC) ---
    schedule="0 6 1 * *",
    start_date=datetime(2025, 1, 1),

    # --- Orchestration: auto-trigger bronze load after ingestion ---
    trigger_dag_id="ine_bronze_load",

    # --- Tags ---
    tags=["ine", "housing", "demographics", "tourism", "economy", "innovation", "quarterly"],
)
