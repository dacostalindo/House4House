# Zome Portugal — Developments + Listings

**Zome Portugal** — 302 developments and 8,975 listings fetched from a Supabase PostgreSQL REST API with a public anon key. Provides ERA-style absorption tracking (available/reserved/sold counts per development) and per-unit status flags. Second-largest development dataset after RE/MAX.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | Zome Portugal |
| API | Supabase REST (PostgREST) at `luvskhnljpxllkxpeasu.supabase.co` |
| Auth | Public anon key (embedded in frontend JS, expires 2032) |
| Schema | `pt_prod` (via `Accept-Profile` header) |
| Format | JSON |
| Coverage | Portugal (national) |
| Refresh | Weekly |

---

## What it fetches

Two Supabase tables, fetched via paginated REST requests:

### `tab_ventures` — 302 developments

| Field | Coverage | Notes |
|-------|----------|-------|
| Development name (`nome`) | 100% | |
| EMID (development code) | 100% | e.g. `EMPT194896` |
| Location (district/municipality/parish) | 100% | 3-level hierarchy |
| GPS coordinates | 98% | lat/lng strings |
| Price | 80% | Formatted string + numeric |
| Typology groups | 98% | e.g. "T1,T2,T3" |
| Units available | 81% | `imoveisdisponiveis` |
| Units reserved | 36% | `imoveisreservados` |
| Units sold | 14% | `imoveisvendidos` |
| Finishing map (PDF) | 100% | Direct URL to acabamento PDF |
| Gallery images | Yes | JSON array (multiple resolutions) |
| Video / Virtual reality | Yes | JSON (YouTube embeds, VR links) |
| Consultant | Yes | Name, email, phone, hub |
| Exclusivity flag | Yes | Boolean |
| Description | Yes | Multi-language JSONB (PT/EN/ES/FR/NL/DE/IT/CN) |

**Aggregate unit status: ~1,700 available + ~440 reserved + ~160 sold = ~2,300 tracked units**

### `tab_listing_list` — 8,975 listings

| Field | Coverage | Notes |
|-------|----------|-------|
| Price | 65% | Formatted string + numeric |
| Previous price (`valorantigo`) | 2% | PT-formatted string (e.g. "1.299.000") |
| Area (useful) | 80% | `areautilhab` m2 |
| Area (gross) | 87% | `areabrutaconst` m2 |
| Bedrooms | 70% | `totalquartossuite` |
| Bathrooms | 79% | `attr_wcs` |
| Garage | 47% | Count + number of spots |
| GPS coordinates | 100% | lat/lng |
| Unit state | 100% | 1=Available (65%), 2=Reserved (33%), 3=Sold (2%) |
| Unit condition | 82% | Novo/Renovado/Usado/Em construcao/etc. (8 levels) |
| Property type | 70% | Apartamento/Moradia/Terreno/etc. |
| Development link | 14% | FK to `tab_ventures` via `idemp` |
| Date entered network | Yes | `dataentradarede` |

### How it complements other sources

| Gap | Zome fills with | Join path |
|-----|-----------------|-----------|
| ERA has unit status but fewer devs | 302 devs with Available/Reserved/Sold counts | Development name + location |
| RE/MAX has 16% unit pricing | 65% unit pricing coverage | Cross-portal dedup |
| No finishing specifications | 100% acabamento PDF links (unique) | Per development |
| No condition classification elsewhere | 8-level system (Novo to Ruina) | Per listing |

---

## How it works

```
GET https://luvskhnljpxllkxpeasu.supabase.co/rest/v1/tab_ventures?select=*&limit=1000
  |  (1 request, 302 rows)
  v
GET .../rest/v1/tab_listing_list?select=*&limit=1000&offset={0..9000}
  |  (10 paginated requests, 1000 rows each, 8975 total)
  v
Upload raw JSON to MinIO:
  s3://raw/zome/tab_ventures/developments/{timestamp}.json
  s3://raw/zome/tab_listing_list/p{0..9}/{timestamp}.json
  |
  v
trigger zome_bronze_load_developments -> trigger zome_bronze_load_listings
```

All requests include Supabase headers: `apikey`, `Authorization: Bearer`, `Accept-Profile: pt_prod`.

---

## How to run

### 1. Trigger the DAG

Runs automatically on a daily schedule (every day at **06:00 UTC**, cron `0 6 * * *`). The two bronze DAGs are auto-triggered in sequence after ingestion completes — no manual intervention required.

To run an out-of-cycle refresh: Airflow UI -> **zome_api_ingestion** -> **Trigger DAG**.

No configuration needed. API key is read from the `ZOME_SUPABASE_KEY` environment variable.

### 2. Where it lands

```
s3://raw/zome/tab_ventures/developments/20260421T221506Z.json
s3://raw/zome/tab_listing_list/p0/20260421T221506Z.json
s3://raw/zome/tab_listing_list/p1/20260421T221506Z.json
...
s3://raw/zome/tab_listing_list/p9/20260421T221506Z.json
```

### 3. Bronze load

After ingestion, two bronze DAGs are auto-triggered in sequence:
1. **`zome_bronze_load_developments`** — loads ventures into PostGIS
2. **`zome_bronze_load_listings`** — loads listings into PostGIS

Both can also be triggered manually from the Airflow UI (no config needed).

---

## DAGs

### `zome_api_ingestion` — Supabase API -> MinIO

```
check_api_availability -> fetch_indicator.expand(11) -> upload_to_minio -> cleanup + log_run_metadata -> trigger_zome_bronze_load_developments -> trigger_zome_bronze_load_listings
```

| Setting | Value |
|---------|-------|
| Schedule | `0 6 * * *` (daily at 06:00 UTC) |
| Indicators | 1 ventures + 10 listing pages = 11 total |
| Rate limit | 0.5s between requests |
| Timeout | 60s per request |
| Orchestration | Auto-triggers both bronze DAGs in sequence |
| Tags | `zome`, `developments`, `listings`, `portal`, `supabase` |

### `zome_bronze_load_developments` — MinIO -> PostGIS

```
list_minio_files -> create_table -> load_records -> validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered) |
| MinIO prefix | `zome/tab_ventures` |
| Idempotency | `ON CONFLICT (venture_id, _scrape_date) DO NOTHING` |
| Tags | `zome`, `bronze`, `developments` |

### `zome_bronze_load_listings` — MinIO -> PostGIS

```
list_minio_files -> create_table -> load_records -> validate_counts
```

| Setting | Value |
|---------|-------|
| Schedule | None (auto-triggered) |
| MinIO prefix | `zome/tab_listing_list` |
| Idempotency | `ON CONFLICT (listing_id, _scrape_date) DO NOTHING` |
| Tags | `zome`, `bronze`, `listings` |

---

## Bronze schema

### `bronze_listings.raw_zome_developments`

One row per development per scrape date. 302 rows per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `venture_id` | INTEGER | Zome development ID |
| `emid` | TEXT | Development code (e.g. `EMPT194896`) |
| `nome` | TEXT | Development name |
| `geocoordinateslat` | TEXT | GPS latitude |
| `geocoordinateslong` | TEXT | GPS longitude |
| `preco` | TEXT | Formatted price (e.g. "1.090.000") |
| `precosemformatacao` | NUMERIC(12,2) | Numeric price |
| `tipologiagrupos` | TEXT | Typologies (e.g. "T1,T2,T3") |
| `imoveisdisponiveis` | INTEGER | Units available |
| `imoveisreservados` | INTEGER | Units reserved |
| `imoveisvendidos` | INTEGER | Units sold |
| `acabamento` | TEXT | Finishing map PDF URL |
| `exclusividade` | BOOLEAN | Exclusive listing flag |
| `idestado` | INTEGER | Development state ID |
| `localizacaolevel1` | TEXT | District |
| `localizacaolevel2` | TEXT | Municipality |
| `localizacaolevel3` | TEXT | Parish |
| `nomeconsultor` | TEXT | Consultant name |
| `emailconsultor` | TEXT | Consultant email |
| `contactoconsultor` | TEXT | Consultant phone |
| `deschub` | TEXT | Hub/office name |
| `dataentradarede` | TEXT | Date entered network |
| `mostrarprecowebsite` | BOOLEAN | Show price on website |
| `descricaocompleta` | JSONB | Multi-language descriptions |
| `gallery` | JSONB | Image URLs (lres/mres/hres) |
| `video` | JSONB | Video embeds |
| `virtualreality` | JSONB | VR tour links |
| `raw_json` | JSONB | Full raw API response |
| `_scrape_date` | DATE | Scrape date |
| `_batch_id` | VARCHAR(50) | Batch identifier |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(50) | Always `'zome_supabase'` |
| `_minio_path` | TEXT | Source file in MinIO |

### `bronze_listings.raw_zome_listings`

One row per listing per scrape date. ~8,975 rows per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment primary key |
| `listing_id` | BIGINT | Zome listing ID |
| `pid` | TEXT | Property ID |
| `idemp` | INTEGER | FK to `tab_ventures` development ID |
| `emid` | TEXT | Development code |
| `nome_emp` | TEXT | Development name |
| `idestadoimovel` | INTEGER | Unit state: 1=Available, 2=Reserved, 3=Sold |
| `idcondicaoimovel` | INTEGER | Condition: 1=New, 2=Renewed, 3=Used, 4=In construction, ... |
| `idtipologia` | INTEGER | Type: 1=Apartment, 2=House, 3=Land, ... |
| `idtiponegocio` | INTEGER | Business type |
| `precoimovel` | TEXT | Formatted price |
| `precosemformatacao` | NUMERIC(12,2) | Numeric price |
| `valorantigo` | TEXT | Previous price (PT format, e.g. "1.299.000") |
| `areautilhab` | NUMERIC(10,2) | Useful/habitable area m2 |
| `areabrutaconst` | NUMERIC(10,2) | Gross construction area m2 |
| `totalquartossuite` | INTEGER | Bedrooms/suites |
| `attr_wcs` | INTEGER | Bathrooms |
| `attr_garagem` | TEXT | Garage flag |
| `attr_garagem_num` | INTEGER | Number of garage spots |
| `attr_elevador` | INTEGER | Elevator flag |
| `geocoordinateslat` | TEXT | GPS latitude |
| `geocoordinateslong` | TEXT | GPS longitude |
| `localizacaolevel1` | TEXT | District |
| `localizacaolevel2` | TEXT | Municipality |
| `localizacaolevel3` | TEXT | Parish |
| `url_detail` | TEXT | Listing detail URL |
| `dataentradarede` | TEXT | Date entered network |
| `reservadozomenow` | BOOLEAN | Reserved via Zome Now |
| `showwebsite` | BOOLEAN | Visible on website |
| `showluxury` | BOOLEAN | Visible on luxury portal |
| `rating` | INTEGER | Listing rating |
| `gallery` | JSONB | Image URLs |
| `raw_json` | JSONB | Full raw API response |
| `_scrape_date` | DATE | Scrape date |
| `_batch_id` | VARCHAR(50) | Batch identifier |
| `_ingested_at` | TIMESTAMPTZ | Ingestion timestamp |
| `_source` | VARCHAR(50) | Always `'zome_supabase'` |
| `_minio_path` | TEXT | Source file in MinIO |

### Indexes

**Developments:**
- `idx_zome_dev_id` — `(venture_id)`
- `idx_zome_dev_scrape` — `(_scrape_date)`
- `idx_zome_dev_loc` — `(localizacaolevel2)`

**Listings:**
- `idx_zome_list_id` — `(listing_id)`
- `idx_zome_list_pid` — `(pid)`
- `idx_zome_list_idemp` — `(idemp)`
- `idx_zome_list_scrape` — `(_scrape_date)`
- `idx_zome_list_state` — `(idestadoimovel)`

---

## Reference tables

The Supabase instance also exposes lookup tables used for decoding IDs:

### Unit condition (`idcondicaoimovel`)

| ID | PT | EN |
|----|----|----|
| 1 | Novo | New |
| 2 | Renovado | Renewed |
| 3 | Usado | Used |
| 4 | Em construcao | In construction |
| 5 | Para recuperar | To rebuild |
| 6 | Ruina | Ruin |
| 7 | Nao Aplicavel | Not applicable |
| 9 | Semi-novo | Semi-new |

### Property type (`idtipologia`)

| ID | PT | EN |
|----|----|----|
| 1 | Apartamento | Apartment |
| 2 | Moradia | House |
| 3 | Terreno | Land |
| 4 | Loja | Store |
| 5 | Escritorio | Office |
| 9 | Quinta | Farm |
| 20 | Predio | Building |

### Business type (`idtiponegocio`)

| ID | Description |
|----|-------------|
| 1 | Sale |
| 2 | Rent |

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Supabase caps at 1000 rows/request | Listings require 10 paginated requests | Handled via 10 APIIndicator instances with offset params |
| `valorantigo` is PT-formatted string | e.g. "1.299.000" instead of numeric | Stored as TEXT in bronze, parsed in dbt silver layer |
| Floor plans mixed into gallery | No dedicated planta field; floor plans are regular JPGs in gallery array | Identifiable by filename patterns or CV classification |
| No energy certificates | Not available in Supabase tables | Complement with SCE data |
| No construction dates | Unlike KW, no completion/start dates | Cross-reference with KW `dwellDate`/`fundDate` |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `ZOME_SUPABASE_KEY` | Environment variable | Public anon key (JWT, expires 2032) |
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` |
| `WAREHOUSE_HOST` | Airflow Variable | `warehouse` |

### Directory structure

```
pipelines/api/zome/
├── __init__.py                       # Package marker
├── zome_config.py                    # Indicators, bronze schema, flatten functions
├── zome_ingestion_dag.py             # DAG: Supabase API -> MinIO
├── zome_bronze_developments_dag.py   # DAG: MinIO -> PostGIS (developments)
├── zome_bronze_listings_dag.py       # DAG: MinIO -> PostGIS (listings)
└── README.md                         # This file
```
