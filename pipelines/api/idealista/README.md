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

### `idealista_bronze_load` — MinIO → PostGIS → Nominatim → dbt

```
list_minio_files ─┐
                  ├→ load_listings → validate_counts → reverse_geocode → trigger_dbt_pipeline
create_table ─────┘
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered by `idealista_ingestion`, or manual) |
| Idempotency | `DELETE WHERE _scrape_date = today` before INSERT |
| Reverse geocode | Incremental — only new `(lat, lon)` pairs not yet in `reverse_geocoded` |
| dbt trigger | `TriggerDagRunOperator` → `dbt_full_pipeline` (all 18 models, ~30s) |
| Tags | `idealista`, `bronze`, `listings`, `postgis` |

---

## Bronze schema

### `bronze_listings.raw_idealista`

Source-oriented: stores raw ZenRows fields as-is (TEXT, JSONB, BIGINT). All parsing and transformation belongs in the silver/dbt layer. One row per listing per scrape date.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `id` | BIGSERIAL | Auto | Primary key |
| `_scrape_date` | DATE | Pipeline | Date of scrape |
| `_batch_id` | VARCHAR(50) | Pipeline | `{YYYYMMDDTHHMMSS}` |
| `_minio_path` | TEXT | Pipeline | MinIO object path |
| `_ingested_at` | TIMESTAMPTZ | DB default | `NOW()` |
| `_source` | VARCHAR(30) | — | Always `'idealista'` |
| `_carried_forward` | BOOLEAN | Pipeline | `TRUE` = detail reused from previous run (not re-fetched) |
| `_property_id` | TEXT | `_property_id` | Internal dedup key |
| `_distrito` | TEXT | Pipeline | Crawl segment distrito |
| `_operation` | TEXT | Pipeline | `'sale'` or `'rent'` |
| `property_id` | TEXT | `property_id` | Idealista listing ID |
| `property_url` | TEXT | `property_url` | Full listing URL |
| `property_type` | TEXT | `property_type` | e.g. `'chalet'`, `'flat'`, `'countryHouse'` |
| `property_subtype` | TEXT | `property_subtype` | e.g. `'andarMoradia'`, `'studio'` (~60% NULL) |
| `property_price` | TEXT | `property_price` | Raw price string |
| `price_currency_symbol` | TEXT | `price_currency_symbol` | e.g. `'€'` |
| `lot_size` | TEXT | `lot_size` | Primary area (useful) — raw |
| `lot_size_usable` | TEXT | `lot_size_usable` | Secondary area (gross) — raw |
| `property_dimensions` | TEXT | `property_dimensions` | Always NULL in current data |
| `bedroom_count` | TEXT | `bedroom_count` | Raw string |
| `bedrooms_count` | TEXT | `bedrooms_count` | Alternate field (some listings use this) |
| `bathroom_count` | TEXT | `bathroom_count` | Raw string |
| `floor` | TEXT | `floor` | e.g. `'bj'`, `'ss'`, `'3'`, `'en'` |
| `floor_description` | TEXT | `floor_description` | Free text floor info |
| `property_features` | JSONB | `property_features` | Array of Portuguese feature strings |
| `property_equipment` | JSONB | `property_equipment` | Array of equipment strings |
| `property_images` | JSONB | `property_images` | Array of image URLs |
| `property_image_tags` | JSONB | `property_image_tags` | Image tag metadata |
| `property_condition` | TEXT | `property_condition` | e.g. `'good'`, `'newdevelopment'`, `'renew'` |
| `property_description` | TEXT | `property_description` | Full listing description |
| `property_title` | TEXT | `property_title` | Listing title |
| `energy_certificate` | TEXT | `energy_certificate` | e.g. `'d'`, `'aplus'`, `'bminus'` |
| `address` | TEXT | `address` | Street address |
| `location_name` | TEXT | `location_name` | Locality name |
| `location_hierarchy` | JSONB | `location_hierarchy` | `[district, municipality, parish]` |
| `latitude` | NUMERIC(10,7) | `latitude` | WGS84 |
| `longitude` | NUMERIC(10,7) | `longitude` | WGS84 |
| `country` | TEXT | `country` | e.g. `'pt'` |
| `agency_name` | TEXT | `agency_name` | Real estate agency |
| `agency_phone` | TEXT | `agency_phone` | Agent contact number |
| `agency_logo` | TEXT | `agency_logo` | Agency logo URL |
| `modified_at` | BIGINT | `modified_at` | Unix timestamp (ms) |
| `status` | TEXT | `status` | e.g. `'active'` |
| `last_deactivated_at` | TEXT | `last_deactivated_at` | When listing went inactive |
| `operation` | TEXT | `operation` | Redundant with `_operation` |

### `_carried_forward` explained

When the incremental detail phase finds a `property_id` already in bronze within the last 30 days, it **skips the API call** and copies the previous detail data into the new day's JSONL with `_carried_forward = TRUE`. This saves ~96% of API calls on subsequent runs. The data is identical to the original fetch — only `_scrape_date` is updated.

On **full refresh**, `unified_listings` includes all rows (both fresh and carried-forward) because carried-forward rows are valid listings. On **incremental runs**, only freshly scraped rows (`_carried_forward = FALSE`) are processed to avoid re-merging unchanged data.

### `bronze_listings.reverse_geocoded`

Coordinate-level lookup table populated by the `reverse_geocode` task. Keyed on `(latitude, longitude)` at `NUMERIC(10,7)` precision — exact match with bronze coordinates. Multiple listings at the same coordinates share one geocoded row.

| Column | Type | Description |
|--------|------|-------------|
| `latitude` | NUMERIC(10,7) | PK (part 1) |
| `longitude` | NUMERIC(10,7) | PK (part 2) |
| `display_name` | TEXT | Full Nominatim display name |
| `road` | TEXT | Street name (e.g. "Rua de Aveiro") |
| `house_number` | TEXT | Door number |
| `postcode` | TEXT | Portuguese postal code (e.g. "3800-123") |
| `city_district` | TEXT | City district / bairro |
| `city` | TEXT | City / town / village |
| `raw_response` | JSONB | Full Nominatim JSON response |
| `_geocoded_at` | TIMESTAMPTZ | When the row was geocoded |

**Source:** Local Nominatim container (`mediagis/nominatim:4.4`) with Portugal OSM data at `http://nominatim:8080`. Rate limit: 0.02s between requests (~50 req/s). Batch commits every 100 rows.

### Indexes

- `idx_idealista_property_id` — `(_property_id)`
- `idx_idealista_scrape_date` — `(_scrape_date)`
- `idx_idealista_operation` — `(_operation, _scrape_date)`
- `idx_idealista_distrito` — `(_distrito)`
- `idx_reverse_geocoded_postcode` — `(postcode)` on `reverse_geocoded`

---

## Silver & Gold — dbt layer

All parsing, type casting, and enrichment happens in dbt models. Bronze stores raw data; silver produces analysis-ready tables.

### Full automation chain

```
idealista_ingestion (daily 03:00)
    → idealista_bronze_load (auto-triggered)
        ├─ list_minio_files ──┐
        │                     ├── load_listings → validate_counts → reverse_geocode → trigger_dbt
        └─ create_table ──────┘
            → dbt_full_pipeline (18 models, ~30s)
```

### Data flow

```
bronze_listings.raw_idealista
    ↓ (view)
staging_dbt.stg_idealista           -- Column rename + aliasing
    ↓
silver_properties.unified_listings  -- Type casting, feature extraction, geocoding
    ↓ (joins)
gold_analytics.dim_geography        -- Spatial join (ST_Within → geo_key)
gold_analytics.dim_property_type    -- Two-pass join (type + subtype → property_type_key)
bronze_listings.reverse_geocoded    -- LEFT JOIN for address enrichment + postal codes
```

### `silver_properties.unified_listings`

Incremental merge on `source_listing_id`. 1,495 unique listings (Aveiro, sale + rent).

**Address enrichment:** Raw Idealista addresses are often just parish/neighborhood names (e.g. "Esgueira", "Sá-Barrocas"). The model LEFT JOINs `reverse_geocoded` to enrich addresses:
- If the raw address lacks a street prefix (Rua, Avenida, Travessa, etc.), use Nominatim's `road` + `house_number`
- If the raw address already has a street prefix, keep it (Idealista's is likely better)
- `postal_code` always comes from Nominatim

**Result:** Street address coverage improved from 58% → 93%. Postal code coverage: 0% → 100%.

**Human-readable property types:** `property_type`, `property_subtype`, `property_type_group` columns carry Portuguese labels directly (e.g. "Apartamento", "Moradia Independente") alongside the FK `property_type_key`.

**Transformation pipeline** (8 CTEs):

| CTE | What it does |
|-----|--------------|
| `source_data` | Filter valid rows; incremental: only fresh rows after last run |
| `deduplicated` / `latest` | `ROW_NUMBER()` by `property_id` — keep most recent scrape |
| `parsed` | Type casting: TEXT → NUMERIC, SMALLINT, VARCHAR. Floor codes (`bj`→-1, `ss`→-2, `st`/`en`→0). Condition labels to Portuguese (`good`→`Bom estado`, `newdevelopment`→`Novo`, `renew`→`Para recuperar`). Energy class normalization (`aplus`→`A+`, `bminus`→`B-`) |
| `with_features` | JSONB extraction via `JSONB_ARRAY_ELEMENTS_TEXT` + regex: construction year, orientation, heating type, num floors, gross/useful area, typology |
| `with_flags` | Boolean feature flags from concatenated text: elevator, parking, terrace, garden, pool, AC, storage, wardrobes, furnished, new development |
| `with_geometry` | PostGIS: `ST_MakePoint` → EPSG:4326 + `ST_Transform` → EPSG:3763 |
| `with_geo` | Spatial join to `dim_geography` via `ST_Within(point, freguesia_geom)` |
| `with_type` | Two-pass join to `dim_property_type`: exact (type+subtype), then fallback (type only) |
| `with_hash` | MD5 dedup hash, price per sqm (useful + gross), lifecycle flags |

**SCD (Slowly Changing Dimension) fields:**

| Column | Full refresh | Incremental merge |
|--------|-------------|-------------------|
| `first_seen_date` | `scrape_date` | Preserved from original insert |
| `initial_price_eur` | `price_eur` | Preserved from original insert |
| `price_change_count` | `0` | `+1` when `price_eur` differs from existing |
| `listing_age_days` | `0` | `last_seen_date - first_seen_date` |
| `_created_at` | `NOW()` | Preserved from original insert |

These are protected via dbt's `merge_update_columns` — excluded columns are never overwritten by the merge.

**Feature extraction coverage** (Aveiro, 1,495 listings):

| Field | Coverage | Source pattern |
|-------|----------|----------------|
| `typology` | 96% | `^T\d` in `property_features` |
| `construction_year` | 50% | `Construído em \d{4}` |
| `orientation` | 23% | `Orientação (.+)` |
| `heating_type` | 23% | `Aquecimento (.+)` / `Não tem aquecimento` |
| `has_ac` | — | `ar condicionado` in equipment |
| `has_wardrobes` | — | `roupeiros embutidos` |
| `has_elevator` | — | `elevador` / `ascensor` |

### `gold_analytics.dim_property_type`

Static dimension (16 rows). Maps Idealista raw `property_type` + `property_subtype` to Portuguese labels.

| type_group | tipo | Count |
|------------|------|-------|
| Apartamento | Apartamento | 948 |
| Moradia | Moradia | 501 |
| Moradia | Moradia Rustica | 46 |

### `gold_analytics.dim_geography`

3,049 rows (mainland + islands). Freguesia-level with CAOP boundaries + Census 2021 demographics. Used for spatial join via `ST_Within`.

### Tests (25 on `unified_listings`, 6 on `dim_property_type`)

- Unique + not_null: `listing_key`, `source_listing_id`
- Accepted values: `source` (idealista), `operation_type` (sale/rent), `condition` (Portuguese), `energy_class` (A+ to G), `property_type` (Apartamento/Moradia/Moradia Rústica/Habitação), `property_type_group` (Apartamento/Moradia)
- Range checks: `price_eur` (100–50M), `latitude` (36.9–42.2), `longitude` (-9.6 to -6.1), `construction_year` (1800–2030)
- Relationships: `geo_key` → `dim_geography`, `property_type_key` → `dim_property_type`
- Warn-level: `postal_code` not_null (some rural areas may lack postcodes)

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
| Discovery pagination overlap | Same listing can appear on multiple pages → duplicate rows in bronze | Deduplication added in ingestion DAG (`dict.fromkeys`); silver deduplicates via `ROW_NUMBER()` |
| `modified_at` ≠ original listing date | ZenRows has no original `listing_date` field | Use `modified_at` as best proxy |
| `construction_year` ~50% coverage | Only present when listing includes "Construído em YYYY" in features | Could parse from `property_description` for additional coverage |
| `property_subtype` ~60% NULL | Many listings only have `property_type` without subtype | Two-pass dim join: exact match first, then fallback to type-only |
| Madeira/Azores not covered | Only 18 continental distritos configured | Add island URLs to `DISTRITO_SEARCH_URLS` when needed |
| `useful_area_m2` vs `gross_area_m2` | `lot_size` is primary (useful), `lot_size_usable` is secondary (gross) | Silver layer uses `COALESCE` with feature-extracted areas as fallback |
| `ACTIVE_DISTRITOS` set to Aveiro only | Config currently limits scheduled runs to Aveiro | Change to `None` in `idealista_config.py` for all 18 distritos |

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
