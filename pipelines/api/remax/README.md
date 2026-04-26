# RE/MAX Portugal — New Developments

**RE/MAX Portugal** — ~661 new development listings with ~8,700 units scraped from the open REST API. Two-pass strategy: paginated search for all developments, then unit detail enrichment for online units. Split into two bronze tables: developments (dev-level) and listings (unit-level with typed columns).

RE/MAX Collection (remaxcollection.pt) is the same API with 100% ID overlap — no separate scrape needed. The `is_special` flag identifies Collection properties.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | RE/MAX Portugal |
| API | `POST https://remax.pt/api/Development/PaginatedSearch` |
| Auth | None required (open API) |
| Format | JSON |
| Coverage | Portugal (national) |
| Refresh | Weekly |

---

## What it fetches

### Pass 1 — Paginated Search (all ~661 developments, ~8,700 units)

| Field | Level | Coverage | Notes |
|-------|-------|----------|-------|
| Development name, GPS, region | Dev | 100% | |
| Min price | Dev | 62% | `minimumPrice` |
| Office/Agent | Dev | 100% | Name, phone, ID |
| isSpecial (Collection) | Dev | 100% | 16 developments flagged |
| Unit price | Unit | ~65% non-zero | `listingPrice` |
| Unit area (total + living) | Unit | ~95% | m2 |
| Bedrooms, bathrooms | Unit | ~97% | |
| Floor | Unit | ~90% | `floorID` + `floorAsNumber` |
| Energy class | Unit | 100% | `energyEfficiencyLevelID` |
| Status | Unit | 100% | `listingStatusID` (1=Available, 2=Reserved) |
| isSold | Unit | 100% | Boolean + `soldDate` |
| isOnline | Unit | 100% | Online units get Pass 2 enrichment |

### Pass 2 — Unit Detail (online units only, ~45%)

| Field | Coverage | Notes |
|-------|----------|-------|
| Address | ~45% | Street-level (e.g. "Rua Antonio da Rocha Madail") |
| Apartment number (fraction) | ~10% | SCE cross-ref key (e.g. "1A", "3.7") |
| Market days | ~45% | Days on market (demand signal) |
| Previous price | ~20% | Price change history |
| Construction year | ~30% | |
| Contract date | ~45% | Listing contract signing date |
| Floor description | ~45% | Text (e.g. "3 Andar") |
| Listing rooms | ~45% | Room-by-room breakdown with m2 areas |
| Unit GPS | ~45% | Unit-level lat/lng |

---

## How it works

```
POST https://remax.pt/api/Development/PaginatedSearch  {pageNumber: 1..14, pageSize: 50}
  |  (14 pages x 50 = ~661 developments with embedded units)
  v
For each online unit (~45%):
  GET https://remax.pt/_next/data/{buildId}/en/imoveis/{slug}/{title}.json
    |  (decode listingEncoded base64 -> address, rooms, marketDays, previousPrice)
    v
Write JSONL to temp dir (1 line per development with enriched listings[])
  |
  v
Upload to MinIO:
  s3://raw/remax_developments/PORTUGAL/{YYYYMMDD}/{timestamp}.jsonl
  |
  v
trigger remax_bronze_load_developments -> trigger remax_bronze_load_listings
```

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **remax_ingestion** -> **Trigger DAG**.

No configuration needed. Single region (Portugal) defined in [remax_config.py](remax_config.py).

### 2. Where it lands

```
s3://raw/remax_developments/PORTUGAL/{YYYYMMDD}/{timestamp}.jsonl
```

### 3. Bronze load

After ingestion, two bronze DAGs are auto-triggered in sequence:
1. **`remax_bronze_load_developments`** — loads dev-level fields
2. **`remax_bronze_load_listings`** — explodes units from JSONL, extracts typed columns + Pass 2 enrichment

Both can also be triggered manually from the Airflow UI (no config needed).

---

## DAGs

### `remax_ingestion` — RE/MAX API -> MinIO

```
check_site_availability -> scrape_region(PORTUGAL) -> upload_to_minio -> cleanup + log_run_metadata -> trigger_remax_bronze_load_developments -> trigger_remax_bronze_load_listings
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Backend | `requests` (no browser needed) |
| Rate limit | 1.0s between requests |
| Timeout | 30s per request |
| Orchestration | Auto-triggers both bronze DAGs in sequence |
| Tags | `remax`, `developments`, `portal`, `s46` |

### `remax_bronze_load_developments` — MinIO -> PostGIS

```
list_minio_files -> create_table -> load_records -> validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered) |
| Idempotency | `ON CONFLICT (development_id, _scrape_date) DO NOTHING` |
| Tags | `remax`, `bronze`, `developments`, `s46` |

### `remax_bronze_load_listings` — MinIO -> PostGIS

```
list_minio_files -> create_table -> load_records -> validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered) |
| Idempotency | `ON CONFLICT (listing_id, development_id, _scrape_date) DO NOTHING` |
| Tags | `remax`, `bronze`, `listings`, `s46` |

---

## Bronze schema

### `bronze_listings.raw_remax_developments`

One row per development per scrape date. ~661 rows per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `development_id` | INTEGER | RE/MAX development ID |
| `name` | TEXT | Development name |
| `slug` | TEXT | URL slug |
| `latitude` | NUMERIC(10,7) | GPS latitude |
| `longitude` | NUMERIC(10,7) | GPS longitude |
| `minimum_price` | NUMERIC(12,2) | Min price across units |
| `region_name1` | TEXT | District |
| `region_name2` | TEXT | Municipality |
| `region_name3` | TEXT | Parish |
| `zip_code` | TEXT | Postal code |
| `listings_count` | INTEGER | Number of units |
| `office_name` | TEXT | RE/MAX office name |
| `office_id` | INTEGER | Office ID |
| `agent_name` | TEXT | Listing agent |
| `agent_phone` | TEXT | Agent phone |
| `description` | TEXT | First description body |
| `publish_date` | TEXT | ISO publish date |
| `is_special` | BOOLEAN | RE/MAX Collection flag |
| `is_special_exclusive` | BOOLEAN | Exclusive Collection flag |
| `building_pictures` | JSONB | Gallery image URLs |
| `raw_json` | JSONB | Full development record (without listings array) |
| `_scrape_date` | DATE | Scrape date |
| `_batch_id` | VARCHAR(50) | Batch identifier |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(50) | Always `'remax_portal'` |
| `_minio_path` | TEXT | Source file in MinIO |

### `bronze_listings.raw_remax_listings`

One row per unit per development per scrape date. ~8,700 rows per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `listing_id` | INTEGER | RE/MAX unit ID |
| `development_id` | INTEGER | FK to developments |
| `listing_price` | NUMERIC(12,2) | Unit price |
| `total_area` | NUMERIC(10,2) | Total area m2 |
| `living_area` | NUMERIC(10,2) | Living area m2 |
| `num_bedrooms` | SMALLINT | Number of bedrooms |
| `num_bathrooms` | SMALLINT | Number of bathrooms |
| `floor_id` | SMALLINT | Floor ID |
| `floor_number` | SMALLINT | Floor number |
| `listing_status_id` | SMALLINT | 1=Available, 2=Reserved |
| `is_sold` | BOOLEAN | Sold flag |
| `sold_date` | TEXT | Date sold |
| `is_online` | BOOLEAN | Currently online |
| `is_active` | BOOLEAN | Active listing |
| `energy_efficiency_level` | SMALLINT | Energy class ID |
| `typology_id` | SMALLINT | Typology (T0-T5+) |
| `listing_type` | TEXT | "Apartamento", "Moradia", etc. |
| `publish_date` | TEXT | First publish date |
| `modified` | TEXT | Last modified date |
| `region_name2` | TEXT | Municipality |
| `region_name3` | TEXT | Parish |
| `garage_spots` | SMALLINT | Number of garage spots |
| `parking` | BOOLEAN | Has parking |
| `is_exclusive` | BOOLEAN | Exclusive listing |
| `is_remax_collection` | BOOLEAN | Collection flag (unit level) |
| `price_reduction_pct` | NUMERIC(5,2) | Price reduction percentage |
| `address` | TEXT | Street address (Pass 2) |
| `apartment_number` | TEXT | Fraction letter (Pass 2) |
| `market_days` | INTEGER | Days on market (Pass 2) |
| `previous_price` | NUMERIC(12,2) | Previous price (Pass 2) |
| `construction_year` | SMALLINT | Year of construction (Pass 2) |
| `contract_date` | TEXT | Contract date (Pass 2) |
| `floor_description` | TEXT | Floor text (Pass 2) |
| `listing_rooms` | JSONB | Room breakdown with m2 (Pass 2) |
| `unit_latitude` | NUMERIC(10,7) | Unit GPS latitude (Pass 2) |
| `unit_longitude` | NUMERIC(10,7) | Unit GPS longitude (Pass 2) |
| `raw_json` | JSONB | Full unit record |
| `_has_detail` | BOOLEAN | Whether Pass 2 enrichment was applied |
| `_scrape_date` | DATE | Scrape date |
| `_batch_id` | VARCHAR(50) | Batch identifier |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(50) | Always `'remax_portal'` |
| `_minio_path` | TEXT | Source file in MinIO |

### Indexes

**Developments:**
- `idx_remax_dev_id` — `(development_id)`
- `idx_remax_dev_scrape` — `(_scrape_date)`
- `idx_remax_dev_region` — `(region_name2)`

**Listings:**
- `idx_remax_list_id` — `(listing_id)`
- `idx_remax_list_dev` — `(development_id)`
- `idx_remax_list_scrape` — `(_scrape_date)`
- `idx_remax_list_status` — `(listing_status_id)`
- `idx_remax_list_sold` — `(is_sold)`

---

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/Development/PaginatedSearch` | POST | List all developments (paginated, 50/page) |
| `/api/Development/SearchFeatured` | GET | 493 featured developments |
| `/api/Development/GetDevelopmentByTitle?developmentPublicId={id}` | GET | Single development |
| `/_next/data/{buildId}/en/imoveis/{slug}/{title}.json` | GET | Unit detail (base64-encoded) |
| `/_next/data/{buildId}/en/empreendimento/{slug}/{id}.json` | GET | Development detail |

### Note: buildId

The `buildId` changes on each deployment. Extracted automatically:
```bash
curl -s "https://remax.pt/en/comprar-empreendimentos" | grep -oE '"buildId":"[^"]*"'
```

### RE/MAX Collection

`remaxcollection.pt` uses the same API — 100% ID overlap confirmed. The `is_special` flag on the development identifies Collection properties. No separate scrape needed.

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Unit prices mostly hidden | Only ~65% of units have non-zero price | `previous_price` available via Pass 2 |
| Detail endpoint requires buildId | Changes on each deployment | Auto-extracted at scrape start |
| Pass 2 only for online units | ~45% of units get enrichment | Offline/sold units have basic data from Pass 1 |
| No per-unit reserved status | `listingStatusID` has values 1, 2, 5 | Complement with ERA (Available/Reserved/Sold) |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` |
| `WAREHOUSE_HOST` | Airflow Variable | `warehouse` |

### Directory structure

```
pipelines/api/remax/
├── __init__.py                       # Package marker
├── remax_config.py                   # Regions, bronze schema, flatten functions
├── remax_scraper.py                  # Two-pass scrape function
├── remax_ingestion_dag.py            # DAG: RE/MAX API -> MinIO
├── remax_bronze_developments_dag.py  # DAG: MinIO -> PostGIS (developments)
├── remax_bronze_listings_dag.py      # DAG: MinIO -> PostGIS (listings)
└── README.md                         # This file
```
