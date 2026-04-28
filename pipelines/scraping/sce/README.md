# SCE — Pre-Energy Certificates (PCE)

**Sistema de Certificacao Energetica** — pre-energy certificates scraped from the SCE portal. Each PCE is issued before a building's occupation license, making it a proxy for upcoming new construction. Includes energy class, address, parish, issuance/validity dates, expert number, and land registry reference.

---

## Source

| Property | Value |
|----------|-------|
| Publisher | ADENE — Agencia para a Energia |
| Page | https://www.sce.pt/pesquisa-certificados/ |
| Auth | None (public portal, Cloudflare Turnstile protected) |
| Format | HTML (server-rendered, AJAX form submissions) |
| Method | nodriver (undetected Chrome) + Xvfb virtual display |
| Coverage | Aveiro, Coimbra, Leiria (3 distritos) |
| Volume | ~80K PCE records for current scope |
| Refresh | Weekly (new pre-certificates issued as construction starts) |

---

## What it contains

One row per pre-energy certificate (PCE) per apartment/fraction. Data is extracted from both the search results table and the detail popup for each certificate.

### Fields

| Field | Source | Description |
|-------|--------|-------------|
| `doc_number` | Table | SCE document number (e.g. `SCE0000399459443`) |
| `morada` | Table | Street address |
| `fracao` | Table | Fraction identifier |
| `localidade` | Table | Locality name |
| `concelho` | Table | Municipality name |
| `estado` | Table | Certificate status (`Valido`, `Revogado`, `Anulado`) |
| `doc_substituto` | Table | Replacement document number (if superseded) |
| `tipo_documento` | Table | Document type (`Pre-Certificado`, `Certificado`) |
| `classe_energetica` | Popup | Energy class: A+, A, B, B-, C, D, E, F |
| `data_emissao` | Popup | Issuance date (YYYY/MM/DD) |
| `data_validade` | Popup | Validity date (YYYY/MM/DD) |
| `freguesia_detail` | Popup | Parish name |
| `perito_num` | Popup | Qualified expert number (e.g. `PQ00883`) |
| `conservatoria` | Popup | Land registry office |
| `sob_o_num` | Popup | Land registry entry number |
| `artigo_matricial` | Popup | Property tax matrix article |
| `fracao_autonoma` | Popup | Autonomous fraction from detail |
| `query_distrito` | Meta | Distrito code used in query |
| `query_concelho` | Meta | Concelho code used in query |
| `query_freguesia` | Meta | Freguesia code used in query |

---

## How to run

### 1. Trigger the DAG

Open the Airflow UI -> **sce_ingestion** -> **Trigger DAG** (no config needed).

### 2. What happens

```
check_site_availability          GET landing page, verify HTTP 200
  |
scrape_region (x3 parallel)      one task per distrito, each:
  |                                - launch Chrome via nodriver + Xvfb
  |                                - navigate to search form
  |                                - iterate all concelhos (fetched from dropdown)
  |                                - for each concelho, iterate all freguesias
  |                                - paginate results (10 per page)
  |                                - extract table data + detail popup
  |                                - save as JSONL to /tmp/
  |
upload_to_minio (x3)             upload JSONL per region
  |
cleanup_temp                     remove /tmp/ directories
log_run_metadata                 structured summary
  |
trigger_downstream               -> sce_bronze_load
```

### 3. Where it lands

```
s3://raw/sce_pce/{distrito_code}/{YYYYMMDD}/{timestamp}.jsonl
```

Example: `s3://raw/sce_pce/01/20260323/20260323T210604Z.jsonl`

### 4. Bronze load

Automatically triggered after ingestion via `sce_bronze_load`. Reads all JSONL from MinIO, flattens records, and inserts into PostGIS.

---

## DAGs

### `sce_ingestion` — SCE Portal -> MinIO

```
check_site_availability -> scrape_region.expand(x3) -> upload_to_minio.expand(x3) -> cleanup_temp + log_run_metadata -> trigger_downstream
```

| Setting | Value |
|---------|-------|
| Schedule | None (manual trigger) |
| Concurrency | 4 parallel scrape tasks (`max_active_tis_per_dag=4`) |
| Execution timeout | 4 hours per region |
| Retries | 2 (with 5 min delay) |
| Tags | `ingestion`, `scraping`, `minio`, `sce`, `energy-certificates`, `pce` |
| Trigger | `sce_bronze_load` on completion |

### `sce_bronze_load` — MinIO -> PostGIS

```
find_new_files -> create_table -> process_files -> log_load_summary -> trigger_downstream
```

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by `sce_ingestion`) |
| Idempotency | DELETE by `_scrape_date` + INSERT (upsert on `doc_number, _scrape_date`) |
| Tags | `sce`, `bronze`, `energy-certificates` |
| Trigger | `dbt_sce_build` on completion |

### `dbt_sce_build` — dbt staging + silver

| Setting | Value |
|---------|-------|
| Schedule | None (triggered by `sce_bronze_load`) |
| Selector | `stg_sce_certificates+` (staging + all downstream models) |
| Tags | `dbt`, `cosmos`, `sce` |

---

## Bronze schema

### `bronze_regulatory.raw_sce_certificates`

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL | Auto-increment PK |
| `doc_number` | VARCHAR(50) | SCE document number |
| `morada` | TEXT | Street address |
| `fracao` | VARCHAR(50) | Fraction |
| `localidade` | VARCHAR(200) | Locality |
| `concelho` | VARCHAR(100) | Municipality |
| `estado` | VARCHAR(50) | Certificate status |
| `doc_substituto` | VARCHAR(50) | Replacement document |
| `tipo_documento` | VARCHAR(50) | Document type |
| `classe_energetica` | VARCHAR(10) | Energy class |
| `data_emissao` | VARCHAR(20) | Issuance date |
| `data_validade` | VARCHAR(20) | Validity date |
| `freguesia_detail` | VARCHAR(200) | Parish name |
| `perito_num` | VARCHAR(50) | Expert number |
| `conservatoria` | VARCHAR(200) | Land registry office |
| `sob_o_num` | VARCHAR(50) | Registry entry number |
| `artigo_matricial` | VARCHAR(100) | Tax matrix article |
| `fracao_autonoma` | VARCHAR(50) | Autonomous fraction |
| `query_distrito` | VARCHAR(10) | Query distrito code |
| `query_concelho` | VARCHAR(10) | Query concelho code |
| `query_freguesia` | VARCHAR(10) | Query freguesia code |
| `_scrape_date` | DATE | Scrape date |
| `_batch_id` | VARCHAR(50) | Batch identifier |
| `_ingested_at` | TIMESTAMPTZ | Load timestamp |
| `_source` | VARCHAR(50) | Always `sce_portal` |
| `_minio_path` | TEXT | Source JSONL path |

### Indexes

- B-tree on `doc_number`
- Composite on `(concelho, classe_energetica)`
- B-tree on `_scrape_date`

### Unique constraint

- `(doc_number, _scrape_date)` — prevents duplicate certificates per scrape run

---

## Staging model (`stg_sce_certificates.sql`)

The dbt staging model applies:
- Deduplication on `doc_number` (latest scrape wins)
- Date parsing from `YYYY/MM/DD` strings to proper DATE type
- Null normalization (empty strings -> NULL)
- Lowercase/trim on text fields

---

## Anti-bot bypass

The SCE portal uses Cloudflare Turnstile. The pipeline bypasses it using:

1. **nodriver** — undetected Chrome automation that avoids bot fingerprinting
2. **Xvfb** — virtual framebuffer so Chrome runs in "headed" mode inside Docker (Turnstile doesn't render at all with nodriver, but headed mode is required for form submissions to work)
3. **Browser restart** — Chrome is restarted every 100 pages to prevent memory leaks

The `Dockerfile.airflow` includes `chromium`, `xvfb`, and `xauth` for this purpose.

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| Scrape speed | ~5s per page (10 records), ~4 records/sec | 4 parallel tasks; early exit on empty results |
| 3-distrito scope | Only Aveiro, Coimbra, Leiria covered | Uncomment regions in `sce_config.py` for full country |
| No geocoding | Addresses are text only, no coordinates | Future: fuzzy match to listings or geocode via Nominatim |
| Detail popup | Requires JS click per certificate row | Adds ~1s overhead per record batch |
| Session timeout | Chrome sessions may timeout on very large distritos | Browser restart interval + task retries handle this |

---

## Configuration

### Environment

| Variable | Where | Value |
|----------|-------|-------|
| `MINIO_ENDPOINT` | Airflow Variable | `minio:9000` |
| `MINIO_ACCESS_KEY` | Airflow Variable | Set via `airflow-init` |
| `MINIO_SECRET_KEY` | Airflow Variable | Set via `airflow-init` |

### Docker requirements

Chromium and Xvfb must be installed in the Airflow image:

```dockerfile
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends chromium xvfb xauth && \
    rm -rf /var/lib/apt/lists/*
```

### Directory structure

```
pipelines/scraping/sce/
├── __init__.py                    # Package marker
├── sce_config.py                  # Regions, DAG config, bronze schema
├── sce_scraper.py                 # nodriver scraping logic (async)
├── sce_ingestion_dag.py           # DAG: SCE portal -> MinIO
├── sce_bronze_dag.py              # DAG: MinIO -> PostGIS
└── README.md                      # This file
```

### Expanding coverage

To scrape all 22 Portuguese distritos:
1. Uncomment the remaining regions in `sce_config.py`
2. Update the DAG description
3. Expect ~1-2 days for a full country scrape (~680K records)
