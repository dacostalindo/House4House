# Idealista — Property Listings, Sale & Rent (Idealista S.A.)

**Idealista.pt** — Portugal's largest real estate portal. Active sale and rental listings fetched via ZenRows Real Estate API. Primary listing source for `unified_listings` and rental yield analysis (Sources S03/S04).

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Idealista S.A. |
| API | ZenRows Real Estate API (`realestate.api.zenrows.com`) |
| Auth | API key (stored as Airflow Variable `ZENROWS_API_KEY`) |
| Format | JSON → JSONL (one JSON object per line) |
| Coverage | 18 continental Portuguese distritos (Madeira/Azores not yet included) |
| Volume | ~80K–120K sale + ~30K–50K rental listings nationally |
| Refresh | Daily snapshots (03:00 UTC) |

---

## What it fetches

Two types of data per listing:

| Phase | Endpoint | Items/call | What it returns |
|-------|----------|------------|-----------------|
| **Discovery** | `/v1/targets/idealista/discovery/` | 20 per page | `property_id`, `property_price`, `bedroom_count`, `property_dimensions`, `property_type`, `operation`, `property_url`, `property_description` |
| **Detail** | `/v1/targets/idealista/properties/{id}` | 1 per call | All discovery fields + `latitude`, `longitude`, `address`, `location_hierarchy`, `energy_certificate`, `property_condition`, `property_features`, `agency_name`, `agency_phone`, `bathroom_count`, `modified_at`, `lot_size`, `lot_size_usable` |

---

## How it works

### Two-phase crawl

Split by **18 distritos × 2 operations** (sale/rent) = **36 segments**. Each segment runs as an independent Airflow task via dynamic task mapping (`.expand()`). Idealista caps search results at ~1,800 listings per URL — individual distritos stay within this limit. Lisboa/Porto may hit the cap; these can be sub-divided by municipality in the config without code changes.

### Incremental detail fetching

On subsequent runs, the detail phase checks which `property_id`s already exist in the bronze table within the last **30 days** (`DETAIL_REFRESH_DAYS`). Only new listings are fetched from ZenRows; existing listings carry forward their previous detail data from MinIO. After 30 days, a listing is re-fetched to capture price/description changes.

| Run | Discovery calls | Detail calls | Savings |
|-----|----------------|--------------|---------|
| First run (Beja/sale) | 12 | 228 | — |
| Subsequent run (~10 new listings) | 12 | ~10 | ~96% |
| Force full refresh | 12 | 228 | 0% |

---

## How to run

### 1. Single-segment test (recommended for first run)

Open the Airflow UI → **idealista_ingestion** → **Trigger DAG w/ config**:

```json
{
  "distrito": "beja",
  "operation": "sale",
  "force_full_refresh": true
}
```

### 2. Full national crawl

Trigger with default config (all distritos, both operations):

```json
{}
```

Or from the CLI:

```bash
docker exec house4house-airflow-scheduler-1 bash -c \
  "airflow dags trigger idealista_ingestion"
```

### 3. Where it lands

#### MinIO (raw layer)

```
s3://raw/idealista/discovery/{operation}/{distrito}/{YYYYMMDD}.jsonl
s3://raw/idealista/detail/{operation}/{distrito}/{YYYYMMDD}.jsonl
```

Each run produces new date-stamped files — full audit trail, no overwrites.

### 4. Bronze load

After ingestion completes, trigger **`idealista_bronze_load`** (no config needed):

```bash
docker exec house4house-airflow-scheduler-1 bash -c \
  "airflow dags trigger idealista_bronze_load"
```

### Trigger parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `distrito` | `"all"` | Single distrito key (e.g. `"beja"`, `"lisboa"`) or `"all"` for all 18 |
| `operation` | `"all"` | `"sale"`, `"rent"`, or `"all"` for both |
| `force_full_refresh` | `false` | Skip incremental check and re-fetch all details |

---

## DAGs

### `idealista_ingestion` — ZenRows API → MinIO

```
check_zenrows_api → build_segments → crawl_discovery.expand(36) → crawl_details.expand(36) → log_run_summary → trigger_bronze_load
```

| Setting | Value |
|---------|-------|
| Schedule | `0 3 * * *` (daily at 03:00 UTC) |
| Default state | **Paused** (unpause when ready for daily runs) |
| `max_active_tasks` | 4 (limits concurrent ZenRows API calls) |
| Orchestration | Auto-triggers `idealista_bronze_load` after completion (`wait_for_completion=True`) |
| Tags | `ingestion`, `api`, `idealista`, `minio`, `listings` |

### `idealista_bronze_load` — MinIO → PostGIS

```
list_minio_files ─┐
                  ├→ load_listings → validate_counts
create_table ─────┘
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered by `idealista_ingestion`, or manual) |
| Idempotency | `DELETE WHERE _scrape_date = today` before INSERT |
| Tags | `idealista`, `bronze`, `listings`, `postgis` |

---

## Bronze schema

### `bronze_listings.raw_idealista`

One row per listing per scrape date. Beja/sale test: 228 rows.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `id` | BIGSERIAL | Auto | Primary key |
| `source_listing_id` | VARCHAR(50) | `property_id` | Deduplication key |
| `listing_url` | TEXT | `property_url` | Full Idealista URL |
| `operation_type` | VARCHAR(10) | `operation` | `'sale'` or `'rent'` |
| `price` | NUMERIC(12,2) | `property_price` | EUR |
| `currency` | CHAR(3) | — | Always `'EUR'` |
| `property_type_raw` | VARCHAR(100) | `property_type` | e.g. `'chalet'`, `'flat'` |
| `property_subtype_raw` | VARCHAR(100) | `property_subtype` | e.g. `'andarMoradia'` |
| `typology_raw` | VARCHAR(20) | `bedroom_count` | Stored as string |
| `useful_area_m2` | NUMERIC(10,2) | `lot_size_usable` | Usable area |
| `gross_area_m2` | NUMERIC(10,2) | `lot_size` | Total built area |
| `plot_area_m2` | NUMERIC(12,2) | `lot_size` | Plot/land area |
| `num_rooms` | SMALLINT | `bedroom_count` | Integer |
| `num_bathrooms` | SMALLINT | `bathroom_count` | Integer |
| `floor_number` | SMALLINT | `floor` | Parsed from string (ground = 0) |
| `has_elevator` | BOOLEAN | `property_features` | Keyword: elevator/lift/elevador |
| `has_parking` | BOOLEAN | `property_features` | Keyword: parking/garagem/estacionamento |
| `has_terrace` | BOOLEAN | `property_features` | Keyword: terrace/terraco/varanda |
| `has_garden` | BOOLEAN | `property_features` | Keyword: garden/jardim |
| `has_pool` | BOOLEAN | `property_features` | Keyword: pool/piscina/swimming |
| `has_ac` | BOOLEAN | `property_equipment` | Keyword: air conditioning/ar condicionado/climatização |
| `has_heating` | BOOLEAN | `property_equipment` | Keyword: heating/aquecimento/calefação |
| `has_balcony` | BOOLEAN | `property_features` | Keyword: balcony/balcão |
| `has_furnished_kitchen` | BOOLEAN | `property_equipment` | Keyword: furnished kitchen/cozinha equipada |
| `has_wardrobes` | BOOLEAN | `property_equipment` | Keyword: built-in wardrobes/armários embutidos/roupeiros |
| `is_exterior` | BOOLEAN | `property_features` | Keyword: exterior |
| `energy_class` | CHAR(2) | `energy_certificate` | Letter grade (A+ to F) |
| `construction_year` | SMALLINT | `property_features` | Parsed from "Construído em YYYY" |
| `condition_raw` | VARCHAR(50) | `property_condition` | e.g. `'good'`, `'to renovate'` |
| `description_text` | TEXT | `property_description` | Full listing description |
| `address_raw` | TEXT | `address` | Street address |
| `district_raw` | VARCHAR(100) | `location_hierarchy[0]` | e.g. `'Beja'` |
| `municipality_raw` | VARCHAR(100) | `location_hierarchy[1]` | e.g. `'Beja'` |
| `parish_raw` | VARCHAR(100) | `location_hierarchy[2]` | e.g. `'Santiago Maior e São João Baptista'` |
| `latitude` | NUMERIC(10,7) | `latitude` | WGS84 |
| `longitude` | NUMERIC(10,7) | `longitude` | WGS84 |
| `listing_date` | DATE | `modified_at` | Best proxy (no original listing date in API) |
| `update_date` | DATE | `modified_at` | Unix timestamp ms → DATE |
| `agent_name` | VARCHAR(200) | `agency_name` | Real estate agency |
| `agent_type` | VARCHAR(50) | — | NULL (not in ZenRows) |
| `agent_phone` | VARCHAR(50) | `agency_phone` | Agent contact number |
| `image_count` | SMALLINT | `property_images` | Count of listing photos |
| `last_deactivated_at` | DATE | `last_deactivated_at` | When listing went inactive |
| `status_raw` | VARCHAR(20) | `status` | e.g. `'active'` |
| `_ingested_at` | TIMESTAMPTZ | DB default | `NOW()` |
| `_source` | VARCHAR(30) | — | Always `'idealista'` |
| `_scrape_date` | DATE | Pipeline | Date of scrape |
| `_batch_id` | VARCHAR(50) | Pipeline | `{YYYYMMDDTHHMMSS}` |
| `_raw_html_path` | TEXT | Pipeline | MinIO object path |

### Indexes

- `idx_idealista_source_id` — `(source_listing_id)`
- `idx_idealista_scrape_date` — `(_scrape_date)`
- `idx_idealista_operation` — `(operation_type, _scrape_date)`
- `idx_idealista_location` — `(district_raw, municipality_raw)`

---

## Field parsing logic

The bronze loader parses ZenRows JSON fields into typed columns:

| Parser | Logic | Example |
|--------|-------|---------|
| `_parse_price` | Strip spaces/commas, cast to float | `125000` → `125000.00` |
| `_parse_area` | Extract first numeric from string | `"95 m²"` → `95.0` |
| `_parse_floor` | Extract integer; ground/rés-do-chão = 0 | `"3rd floor"` → `3` |
| `_parse_bool_feature` | Case-insensitive substring search in features list | `["Elevador", ...]` → `has_elevator = true` |
| `_parse_energy_class` | Extract letter grade; isento/exempt = NULL | `"d"` → `"D"` |
| `_parse_construction_year` | Regex on features: "Construído em YYYY" | `"Construído em 1969"` → `1969` |
| `_parse_location_hierarchy` | Positional: `[district, municipality, parish]` | `["Beja", "Beja", "Santiago Maior..."]` |
| `_parse_date` (modified_at) | Unix timestamp ms → YYYY-MM-DD | `1770624998000` → `2026-02-09` |

---

## ZenRows API response structure

### Discovery response

```json
{
  "pagination": {
    "current_page": 1,
    "items_count": 228,
    "items_per_page": 20,
    "page_count": 12
  },
  "property_list": [
    {
      "property_id": 34729761,
      "property_price": 125000,
      "bedroom_count": 1,
      "property_dimensions": "41 m²",
      "property_type": "chalet",
      "operation": "sale",
      "property_url": "https://www.idealista.pt/imovel/34729761/",
      "property_title": "Andar de moradia...",
      "property_description": "...",
      "property_image": "https://...",
      "price_currency_symbol": "€"
    }
  ]
}
```

### Detail response

```json
{
  "property_id": 34729761,
  "property_price": 125000,
  "bedroom_count": 1,
  "bathroom_count": 1,
  "latitude": 38.0165814,
  "longitude": -7.8633407,
  "address": "Rua de São Gregorio, 13",
  "location_hierarchy": ["Beja", "Beja", "Santiago Maior e São João Baptista"],
  "location_name": "Santiago Maior e São João Baptista, Beja",
  "energy_certificate": "d",
  "property_condition": "good",
  "property_features": [
    "Andar de moradia", "Rés do chão", "42 m² construídos, 34 m² úteis",
    "T1", "1 casa de banho", "Segunda mão/bom estado", "Construído em 1969"
  ],
  "agency_name": "Montra Digital",
  "agency_phone": "281025747",
  "modified_at": 1770624998000,
  "lot_size": 42,
  "lot_size_usable": 34,
  "operation": "sale",
  "property_type": "chalet",
  "property_subtype": "andarMoradia",
  "status": "active",
  "property_url": "https://www.idealista.pt/imovel/34729761",
  "property_images": ["..."],
  "property_image_tags": ["..."]
}
```

---

## Verified test results (Beja/sale, 2026-03-03)

| Metric | Value |
|--------|-------|
| Listings discovered | 228 |
| Details fetched | 228 (0 errors) |
| Discovery API calls | 12 pages |
| Detail API calls | 228 |
| Total API calls | 241 |
| Discovery time | ~50 seconds |
| Detail time | ~11 minutes |
| With coordinates | 228 (100%) |
| With district/municipality/parish | 228 (100%) |
| With energy class | 207 (91%) |
| With construction year | 99 (43%) |
| With agent name | 190 (83%) |
| Avg price | €366,511 |
| Avg area | 184 m² |
| Avg rooms | 3.7 |

---

## Rate limiting & costs

| Constant | Value | Purpose |
|----------|-------|---------|
| `DISCOVERY_RATE_LIMIT_SECONDS` | 2.0 | Sleep between discovery page requests |
| `DETAIL_RATE_LIMIT_SECONDS` | 1.5 | Sleep between detail requests |
| `DETAIL_REFRESH_DAYS` | 30 | Skip detail for listings seen in last N days |
| `max_active_tasks` | 4 | Max concurrent Airflow tasks per DAG run |

### Estimated API calls per national run

| Phase | First run | Incremental run |
|-------|-----------|-----------------|
| Discovery (all distritos, sale+rent) | ~6,000–8,000 | ~6,000–8,000 (always full) |
| Detail (all listings) | ~110,000–170,000 | ~5,000–15,000 (new only) |
| **Total** | **~120,000–180,000** | **~12,000–22,000** |

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Lisboa/Porto may exceed 1,800 listing cap | Idealista caps search at ~1,800 results per URL | Log warning when hit; split by municipality in `DISTRITO_SEARCH_URLS` config |
| `modified_at` ≠ original listing date | ZenRows has no original `listing_date` field | Use `modified_at` as best proxy; documented in column mapping |
| `construction_year` only 43% coverage | Only present when listing includes "Construído em YYYY" in features | Silver layer may parse from description text for additional coverage |
| `agent_type` always NULL | ZenRows does not expose agent type | No resolution needed — not critical for analysis |
| Madeira/Azores not covered | Only 18 continental distritos configured | Add island URLs to `DISTRITO_SEARCH_URLS` when needed |
| `useful_area_m2` vs `gross_area_m2` | ZenRows has `lot_size_usable` and `lot_size` but distinction is imperfect | Silver layer to reconcile using `property_features` text |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `ZENROWS_API_KEY` | Airflow Variable | Set via `airflow-init` in `docker-compose.yml`, sourced from `.env` |
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `WAREHOUSE_HOST` | Airflow Variable | `warehouse` |

### Directory structure

```
pipelines/api/idealista/
├── __init__.py                    # Package marker
├── idealista_config.py            # Search URLs, rate limits, constants
├── idealista_ingestion_dag.py     # DAG: ZenRows → MinIO (discovery + detail)
├── idealista_bronze_dag.py        # DAG: MinIO → PostGIS bronze table
└── README.md                      # This file
```

### Modifying configuration

All configuration lives in [idealista_config.py](idealista_config.py). To add a new distrito or change rate limits, edit the constants there — no DAG code changes needed.
