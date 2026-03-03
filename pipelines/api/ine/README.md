# INE API Ingestion — Housing, Demographics, Tourism, Economy & Innovation

**Instituto Nacional de Estatística** — 33 statistical indicators fetched from the public JSON API. Time-series housing market data that complements the static BGRI Census 2021 snapshot.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | INE — Instituto Nacional de Estatística |
| API | `https://www.ine.pt/ine/json_indicador/pindica.jsp` |
| Auth | None required (public API) |
| Format | JSON (raw, stored as-is in MinIO bronze layer) |
| CRS | N/A (tabular data with NUTS geographic codes) |
| Refresh | Quarterly (most indicators), some monthly |

---

## What it fetches

33 indicators across 6 categories:

### Housing: prices (4)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0009201` | House Price Index (Base 2015) | Quarterly | National |
| `0009207` | Commercial Property Price Index (Base 2015) | Annual | National |
| `0012234` | Median Dwelling Sales Value by Sector | Quarterly | NUTS-2024 |
| `0012235` | Median Flat Sales Value | Quarterly | NUTS-2024 |

### Housing: transactions (4)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012785` | Housing Transactions Count | Quarterly | NUTS-2024 |
| `0012786` | Housing Transactions Value (€) | Quarterly | NUTS-2024 |
| `0012787` | Housing Transactions Count | Annual | NUTS-2024 |
| `0012788` | Housing Transactions Value (€) | Annual | NUTS-2024 |

### Housing: rental market (4)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012571` | Median Rental Value (€/m²) | Quarterly | NUTS-2024 |
| `0012572` | New Lease Agreements Count | Quarterly | NUTS-2024 |
| `0012573` | Median Rental Value (€/m²) — Large cities | Quarterly | Municipalities >100k |
| `0012574` | New Lease Agreements — Large cities | Quarterly | Municipalities >100k |

### Housing: construction (3)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012096` | Licensed Buildings | Monthly | NUTS-2024 |
| `0012778` | Completed Dwellings (New Construction) | Quarterly | NUTS-2024 |
| `0011750` | Housing Construction Cost Index | Monthly | National |

### Housing: mortgage finance (4)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0006340` | Housing Loan Interest Rate | Monthly | National |
| `0006341` | Housing Loan Outstanding Liability (€) | Monthly | National |
| `0008867` | Housing Loan Interest Rate by NUTS I | Monthly | NUTS-I |
| `0008870` | Total Interests on Housing Loans by NUTS I | Monthly | NUTS-I |

### Housing: sales — updated methodology (1)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012236` | Median Dwelling Sales Value per m² (2022 methodology) | Quarterly | NUTS-2024 + municipalities |

### Housing: construction — additional (2)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012097` | Licensed Dwellings (New Construction) | Monthly | NUTS-2024 |
| `0008321` | Completed Dwellings (New Construction) | Annual | NUTS + municipalities |

### Housing: building stock — Census 2021 (2)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0012575` | Building Aging Index | Decennial | Parish |
| `0012581` | Buildings Needing Repair (%) | Decennial | Parish |

### Demographics (3)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0001271` | Old-age Dependency Ratio | Annual | National |
| `0008273` | Resident Population by Sex & Age Group | Annual | NUTS + municipalities |
| `0008337` | Population Density (per km²) | Annual | Municipalities |

### Tourism (1)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0009808` | Tourism Overnight Stays | Monthly | NUTS regions |

### Economy (2)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0008351` | Consumer Price Index (CPI, Base 2012) | Annual | NUTS-II |
| `0011190` | GDP per Capita in PPC (EU27) | Annual | NUTS |

### Innovation & technology (3)

| Code | Name | Frequency | Geography |
|------|------|-----------|-----------|
| `0008515` | ICT Companies Count | Annual | NUTS + municipalities |
| `0008519` | Gross Value Added in ICT Activities (€) | Annual | NUTS + municipalities |
| `0008521` | High & Medium-High Technology Companies | Annual | NUTS + municipalities |

---

## How it complements BGRI

| Gap in BGRI | INE API fills with | Join path |
|---|---|---|
| No price trends | Median sales €/m² (quarterly, NUTS-2024) | BGRI subsection → municipality → NUTS code |
| No transaction volume | Transaction count/value (quarterly) | Same |
| No rental data | Median rental €/m² (quarterly, NUTS-III) | Same |
| No construction activity | Licensed buildings, completed dwellings | Same |
| No financing context | Loan interest rates, outstanding liability | NUTS-I broadcast |
| Static 2021 snapshot | Time-series 2009–present | Temporal enrichment |

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI → **ine_api_ingestion** → **Trigger DAG**.

No configuration parameters needed — all indicator codes are defined in [ine_config.py](ine_config.py).

### 2. What happens

```
GET https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd={code}&Dim1=T&lang=EN
  ↓  (×33 indicators, sequential with 1s delay, 3 retries each)
raw JSON saved to temp dir
  ↓
upload to MinIO as-is:
  s3://raw/ine/{code}/{timestamp}.json
  ↓
cleanup temp dirs
log_run_metadata (structured summary)
```

### 3. Where it lands

```
s3://raw/ine/0009201/20260301T060000Z.json
s3://raw/ine/0009207/20260301T060000Z.json
...
s3://raw/ine/0001271/20260301T060000Z.json
```

Each run appends a new timestamped file — full audit trail, no overwrites.

---

## JSON response structure

The INE API returns data nested inside a `Dados` dict keyed by period:

```json
{
  "IndicadorCod": "0009201",
  "IndicadorDsg": "Housing price index...",
  "DataExtracao": "2026-02-23T20:35:28.002Z",
  "DataUltimoAtualizacao": "2025-06-18",
  "Dados": {
    "2024": [{"geocod": "PT", "geodsg": "Portugal", "valor": "38.6", ...}],
    "2023": [...]
  }
}
```

Key fields inside each observation: `geocod`, `geodsg`, `valor`, `ind_string`, `dim_3`/`dim_3_t` (indicator-specific dimensions), `sinal_conv` (convention codes for missing data).

---

## Bronze Schema

After ingestion to MinIO, DAG **`ine_bronze_load`** flattens the JSON files into PostGIS.
Full-refresh per indicator (DELETE + INSERT), idempotent, no schedule — trigger manually.

### `bronze_ine.raw_indicators` — 907,533 rows (33 indicators)

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `indicator_code` | VARCHAR(20) | INE code (e.g. `'0009201'`) |
| `indicator_name` | TEXT | Full description from `IndicadorDsg` |
| `last_updated` | DATE | `DataUltimoAtualizacao` from INE |
| `time_period` | VARCHAR(50) | Period key (e.g. `'2024'`, `'1st Quarter 2009'`, `'April 2007'`) |
| `geocod` | VARCHAR(20) | INE geographic code (e.g. `'PT'`, `'1106'`, `'11E'`) |
| `geodsg` | VARCHAR(200) | Geographic name (e.g. `'Portugal'`, `'Lisboa'`) |
| `dim_3` | VARCHAR(20) | Dimension 3 code (indicator-specific, e.g. `'H11'`) |
| `dim_3_t` | VARCHAR(200) | Dimension 3 label (e.g. `'New'`) |
| `dim_4` | VARCHAR(20) | Dimension 4 code (some indicators only) |
| `dim_4_t` | VARCHAR(200) | Dimension 4 label |
| `dim_5` | VARCHAR(20) | Dimension 5 code (rare) |
| `dim_5_t` | VARCHAR(200) | Dimension 5 label |
| `valor` | NUMERIC(15,4) | Parsed numeric value (NULL when missing) |
| `ind_string` | VARCHAR(50) | Raw formatted string (e.g. `'104,55'`, `'x'`) |
| `sinal_conv` | VARCHAR(10) | Convention code (e.g. `'x'` = not available) |
| `sinal_conv_desc` | VARCHAR(100) | Convention description |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(50) | Always `'ine_api'` |
| `_batch_id` | VARCHAR(50) | Batch identifier (e.g. `'0009201_20260302T212500'`) |
| `_api_extraction_ts` | TIMESTAMPTZ | `DataExtracao` from INE response |

### Indexes

- `idx_ine_ind_code` — `(indicator_code)`
- `idx_ine_ind_period` — `(indicator_code, time_period)`
- `idx_ine_ind_geo` — `(indicator_code, geocod)`

### Top indicators by row count

| Code | Name | Rows | Geographic granularity |
|------|------|------|----------------------|
| `0008273` | Resident population | 254,904 | Municipalities |
| `0008321` | Completed dwellings | 240,520 | Municipalities |
| `0012096` | Licensed buildings | 80,028 | NUTS |
| `0012236` | Median sales €/m² | 67,032 | Municipalities |
| `0012234` | Median dwelling sales | 67,032 | NUTS |
| `0012097` | Licensed dwellings | 44,460 | NUTS |

---

## After ingestion

Trigger **`ine_bronze_load`** from the Airflow UI (no config needed).
It reads the latest JSON per indicator from MinIO automatically.

---

## Adding indicators

Add a new `APIIndicator` entry to `INE_INDICATORS` in [ine_config.py](ine_config.py).
Then add the code to `INDICATOR_CODES` in [ine_bronze_dag.py](ine_bronze_dag.py).
No other code changes needed.

To find indicator codes:
1. Browse https://www.ine.pt → choose a dataset → inspect URL for `varcd=XXXXXXX`
2. Search the metadata service: http://smi.ine.pt/Indicador
