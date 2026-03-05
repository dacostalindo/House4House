# House4House

# Portugal Real Estate Data Warehouse — MVP Blueprint
## Complete Technical Architecture: Sources, Stack, Models & Delivery Plan
### Scoped to 24 Data Sources (P0 + P1 + P2) for Minimum Viable Product

---

## Table of Contents

1. Business Use Cases
2. MVP Data Sources (24 Sources)
3. Technology Stack
4. Infrastructure & Deployment
5. Conceptual Architecture (Medallion Pattern)
6. Data Flows by Source Type
7. Conceptual Data Models
8. Physical Data Models — All Layers
9. Spatial Data Strategy
10. Dependency Graph & Critical Path
11. Orchestration & Scheduling
12. Sprint Plan (8 Sprints / 16 Weeks)
13. Data Quality Framework
14. Risk Register & Mitigation
15. Resource Requirements & Costs
16. Future Expansion (P3/P4 Roadmap)

---

# Part I — Business Context & Data Sources

---

## 1. Business Use Cases

### UC-1: Undervalued Property Identification

**Users:** Real estate investors, property promoters, fund managers, flippers

**Business Questions:**
- Which properties on the market are priced below their predicted fair value?
- Which neighbourhoods are on an upward trajectory where prices haven't caught up to fundamentals?
- Where can I buy, renovate, and sell/rent at the highest ROI?
- What rental yield (long-term and short-term) does each property offer?
- What infrastructure or regulatory catalysts will drive future appreciation?

**Decision Output:** A ranked list of investment opportunities with a composite score combining valuation gap, yield potential, renovation upside, neighbourhood momentum, and catalyst proximity.

**What makes a property undervalued:**
- Listed price is significantly below the predicted price for its characteristics and location
- The neighbourhood is on an upward trajectory (gentrification, infrastructure investment, demographic shift) but prices haven't caught up yet
- The property has renovation potential where post-renovation value substantially exceeds acquisition + renovation cost
- STR yield potential exceeds the asking price justification
- Regulatory tailwinds exist (ARU tax benefits, new metro line, zoning change)

**Analytical layers needed:**
1. **Hedonic pricing model** — predicted fair value based on property attributes and location
2. **Residual analysis** — gap between asking price and predicted value (the "alpha")
3. **Neighbourhood trajectory scoring** — is this area appreciating, stable, or declining?
4. **Renovation upside model** — cost to renovate vs. post-renovation value
5. **Yield analysis** — rental yield and STR yield relative to acquisition price
6. **Catalyst detection** — upcoming infrastructure, zoning changes, ARU designation

### UC-2: New Housing Unit Pricing Strategy

**Users:** Real estate developers/promoters, commercial directors, project managers

**Business Questions:**
- What is the optimal asking price per sqm for each unit in my new development?
- How much premium can I charge for higher floors, river views, south-facing orientation?
- How does my pricing compare to competing developments within 2km?
- At price X, how many months will it take to sell all units?
- What is the minimum price per unit to achieve our target margin?

**Decision Output:** A unit-level pricing recommendation with floor/view/orientation premiums, competitive positioning, absorption forecast, and margin analysis.

**Analytical layers needed:**
1. **Comparable sales engine** — find the most similar recent transactions/listings
2. **Hedonic price decomposition** — isolate the value contribution of each attribute
3. **Micro-location premium model** — quantify €/sqm impact of every location feature
4. **Competitive supply analysis** — new development pipeline and their pricing
5. **Absorption rate forecasting** — time-to-sell based on pricing strategy
6. **Sensitivity analysis** — price elasticity by segment and location

---

## 2. MVP Data Sources (24 Sources)

### 2.1 Scope Decision

This MVP retains **24 data sources** (P0 + P1 + P2) and defers 13 sources (P3 + P4). All deferred fields are nullable in the data models — when P3/P4 sources are added later, the models automatically incorporate them without schema changes.

**Deferred sources and their impact on models:**

| Cut ID | Source | Impact on Models |
|---|---|---|
| S07 | Casa Sapo (third listing portal) | Listings coverage drops ~5-10%; acceptable for MVP |
| S13 | ADENE Energy Certificates | Use `energy_class` from listing data instead; lose kWh/m² detail |
| S21 | INE Building Permits | Remove from trajectory model; use listing volume trends as proxy |
| S25 | IMPIC Construction Costs | Use simplified cost lookup table based on market research |
| S27 | Municipal Noise Maps | Remove `noise_level_db` from hedonic model; minor accuracy loss |
| S28 | PVGIS Solar Potential | Use simplified orientation premium reference table |
| S30 | Porta 65 Rent Caps | Use listing-based rental comps instead |
| S33 | Google Trends | Remove from trajectory model; listing volume trends as demand proxy |
| S35 | APA Flood Risk | Remove `flood_risk_level` from hedonic model; add post-MVP |
| S36 | ICNF Fire Risk | Remove from models entirely; minimal impact in urban areas |
| S26 | DGPC Heritage | Remove `is_heritage_protected` from renovation model |
| S32 | PORDATA | Census 2021 (S12) provides equivalent data at freguesia level |
| S37 | Municipal Open Data | OSM (S09) already covers POIs, green spaces, amenities |

### 2.2 Source-to-Use-Case Mapping

| # | Data Source | UC-1 | UC-2 | Tier |
|---|---|:---:|:---:|---|
| S08 | CAOP Boundaries (DGT) | ● | ● | P0 |
| S12 | INE Census 2021 | ● | ● | P0 |
| S01 | INE — Transaction Prices | ● | ● | P0 |
| S03 | Idealista — Sale Listings | ● | ● | P0 |
| S04 | Idealista — Rental Listings | ● | ○ | P0 |
| S09 | OpenStreetMap — POIs | ● | ● | P0 |
| S10 | OpenStreetMap — Transport Stops | ● | ● | P0 |
| S11 | OpenStreetMap — Road Network (OSRM) | ● | ● | P0 |
| S17 | ECB — Euribor Rates | ● | ● | P0 |
| S16 | Banco de Portugal (BPStat) | ● | ● | P0 |
| S05 | Imovirtual — Sale Listings | ● | ● | P1 |
| S15 | Inside Airbnb | ● | ○ | P1 |
| S18 | Eurostat — House Price Index | ● | ● | P1 |
| S19 | PDM Zoning (Lisbon + Porto) | ● | ● | P1 |
| S31 | AT — IMI/IMT Tax Rates | ● | ○ | P1 |
| S02 | Confidencial Imobiliário (SIR) | ● | ● | P2 |
| S06 | Imovirtual — Rental Listings | ● | ○ | P2 |
| S14 | RNAL — AL Licenses | ● | ○ | P2 |
| S20 | ARU Boundaries | ● | ○ | P2 |
| S22 | InfoEscolas — School Quality | ● | ● | P2 |
| S23 | SNS — Healthcare Facilities | ● | ● | P2 |
| S24 | GTFS — Transport Schedules | ● | ● | P2 |
| S29 | INE — Rental Price Index | ● | ○ | P2 |
| S34 | Competitive Developments (scraped) | ○ | ● | P2 |

**Legend:** ● = Critical | ○ = Enrichment

### 2.3 Detailed Source Specifications

#### P0 — Foundation (10 sources)

**S08 — CAOP Boundaries (DGT)**
- **URL:** https://www.dgterritorio.gov.pt
- **Data:** Official administrative boundaries — distrito, concelho, freguesia polygons
- **Format:** Shapefile, GeoPackage
- **Ingestion:** Download → `ogr2ogr` → PostGIS
- **Volume:** ~3,100 freguesia polygons, ~308 concelhos, ~18 distritos
- **Refresh:** Annual
- **Role:** Foundation for dim_geography; every entity resolves to a freguesia

**S12 — INE Census 2021 (BGRI)**
- **URL:** https://mapas.ine.pt/download/index2021.phtml
- **Data:** 32 census variables per statistical subsection (city-block level) with embedded geometry. Covers buildings (stock, age, typology, repair needs), dwellings (total, vacant, owner-occupied, rented, parking), households (size, family nuclei), and population (total, sex, age bands 0-14 / 15-24 / 25-64 / 65+).
- **Format:** GeoPackage (`.gpkg`) — BGRI (Base Geográfica de Referenciação de Informação). Two layers: `subsecção` (most granular, ~200K polygons) and `secção` (statistical section, aggregated).
- **Source file:** `https://mapas.ine.pt/download/filesGPG/2021/portugal2021.zip` (continental + islands)
- **Ingestion:** GIS file download → MinIO → PostGIS. **Flow C — reuses GIS ingestion template (same as CAOP).**
- **Volume:** ~200K subsection polygons, 32 wide-format columns + geometry. ~200-400 MB GeoPackage.
- **Refresh:** Static — Census 2021. Next census ~2031. Education, employment, and foreign-born not in BGRI synthesis file; to be sourced from INE API (pindica.jsp) as supplementary P1 indicators.
- **Role:** Block-level demographics for hedonic model, trajectory scoring, and dim_geography enrichment. Finer granularity than parish level — directly usable for spatial joins against listings.

**S01 — INE Transaction Prices**
- **URL:** https://www.ine.pt (API: `ine_api`)
- **Indicators:** Median price/sqm (0010694), Transaction count (0010693)
- **Geographic granularity:** Municipality, some at freguesia level
- **Time granularity:** Quarterly
- **Format:** JSON (API)
- **Ingestion:** REST API → Python `requests` → Bronze
- **Volume:** ~500K records (all indicators, all periods, all geographies)
- **Refresh:** Quarterly, ~60 days after quarter end
- **Role:** Ground truth for actual transaction prices; calibrates hedonic model

**S03/S04 — Idealista (Sale + Rental Listings)**
- **URL:** https://www.idealista.pt / https://developers.idealista.com
- **Data:** Active listings — price, area, typology, location, features, photos, agent, listing date
- **Format:** JSON (API)
- **Ingestion:** REST API (developer key, rate-limited) → Bronze
- **Volume:** ~80K-120K active sale listings; ~30K-50K rental listings nationally
- **Refresh:** Daily snapshots
- **Rate limits:** ~100 requests/month (API); scraping as fallback with Scrapy + proxies
- **Role:** Primary listing source for unified_listings; rental comps for yield analysis

**S09 — OpenStreetMap POIs**
- **URL:** https://download.geofabrik.de/europe/portugal.html
- **Data:** Restaurants, cafés, supermarkets, pharmacies, banks, gyms, parks, etc.
- **Format:** PBF (Protocol Buffer Binary)
- **Ingestion:** Download PBF → `osm2pgsql` → PostGIS; or Overpass API for targeted queries
- **Volume:** ~500K POI nodes for Portugal
- **Refresh:** Monthly
- **Role:** Walkability scoring, amenity density for hedonic model and location scores

**S10 — OpenStreetMap Transport**
- **Source:** Same PBF as S09
- **Data:** Metro stations, train stations, bus stops, tram stops
- **Ingestion:** `osm2pgsql` with custom style file filtering `railway=*`, `highway=bus_stop`, `public_transport=*`
- **Volume:** ~30K transport-related nodes
- **Refresh:** Monthly
- **Role:** Transport accessibility scoring

**S11 — OpenStreetMap Road Network**
- **Source:** Same PBF as S09
- **Data:** Full road network for OSRM routing engine
- **Ingestion:** Download PBF → OSRM `osrm-extract` → `osrm-partition` → `osrm-customize` → HTTP API
- **Volume:** ~5GB processed routing graph
- **Refresh:** Monthly
- **Role:** Drive-time isochrone computation (city center, airport, beach)

**S17 — ECB Euribor Rates**
- **URL:** https://sdw.ecb.europa.eu
- **Data:** Euribor 3M, 6M, 12M monthly rates
- **Format:** SDMX-JSON (API)
- **Ingestion:** SDMX REST API → `pandasdmx` → Bronze
- **Volume:** ~5K observations (daily, multi-year)
- **Refresh:** Daily (weekdays)
- **Role:** Interest rate environment for yield analysis and affordability modelling

**S16 — Banco de Portugal (BPStat)**
- **URL:** https://bpstat.bportugal.pt
- **Data:** Mortgage lending volumes, average interest rates, LTV ratios, household debt
- **Format:** JSON/CSV (REST API)
- **Ingestion:** BPStat API → Python `requests` → Bronze
- **Volume:** ~50K time series observations
- **Refresh:** Monthly
- **Role:** Lending conditions context for investment yield and market trajectory

#### P1 — Core (5 sources)

**S05 — Imovirtual (Sale Listings)**
- **URL:** https://www.imovirtual.com
- **Data:** Same structure as Idealista (price, area, typology, location, features)
- **Format:** HTML (no API)
- **Ingestion:** Scrapy + Selenium (JS-rendered) → raw HTML → BeautifulSoup parser → Bronze
- **Volume:** ~50K-70K active sale listings
- **Refresh:** Daily/Weekly
- **Role:** Second listing portal for cross-portal dedup and market coverage

**S15 — Inside Airbnb**
- **URL:** http://insideairbnb.com/get-the-data/
- **Data:** Airbnb listing data for Lisbon and Porto — price, reviews, availability, host
- **Format:** CSV (gzipped)
- **Ingestion:** Direct HTTP download → gunzip → CSV load → Bronze
- **Volume:** ~25K listings per city per snapshot
- **Refresh:** Quarterly
- **Role:** STR performance metrics (occupancy, ADR) for STR yield analysis

**S18 — Eurostat House Price Index**
- **URL:** https://ec.europa.eu/eurostat
- **Data:** HPI for Portugal (2015=100), HICP
- **Format:** JSON/TSV (API)
- **Ingestion:** Eurostat API → `pandasdmx` or `eurostat` Python lib → Bronze
- **Volume:** ~1K observations
- **Refresh:** Quarterly
- **Role:** Macro price trend; calibration benchmark

**S19 — PDM Zoning (Lisbon, Porto)**
- **URL:** https://geodados-cml.hub.arcgis.com (Lisbon), https://portal.amp.pt (Porto)
- **Data:** Zoning polygons with classification, max height, density index
- **Format:** Shapefile, GeoJSON, ArcGIS REST
- **Ingestion:** Download Shapefile → `ogr2ogr` → PostGIS; or ArcGIS REST API → GeoJSON → PostGIS
- **Volume:** ~10K zone polygons for LX+Porto
- **Refresh:** Static (PDM revision ~every 10 years)
- **Role:** Buildability flags, zoning category for hedonic model and development feasibility

**S31 — Autoridade Tributária (IMI/IMT Rates)**
- **URL:** https://info.portaldasfinancas.gov.pt
- **Data:** IMI rates per municipality (annual property tax); IMT brackets (transfer tax)
- **Format:** HTML tables
- **Ingestion:** HTML scrape → structured reference tables
- **Volume:** ~308 municipalities × rates + ~10 IMT brackets
- **Refresh:** Annual (January)
- **Role:** Tax computation for net yield analysis; IMT as transaction cost in investment models

#### P2 — Enhancement (9 sources)

**S02 — Confidencial Imobiliário (SIR Index)**
- **URL:** https://ci-iberica.com
- **Data:** Transaction-based residential price index, median values by parish
- **Format:** CSV/XLSX (licensed) or PDF
- **Ingestion:** Commercial API/SFTP → Bronze; or PDF → tabula-py → Bronze
- **Volume:** ~10K records/quarter
- **Refresh:** Monthly/Quarterly
- **Cost:** Commercial license required (~€2,000-10,000/year)
- **Role:** Transaction-based pricing data at parish level; more granular than INE

**S06 — Imovirtual (Rental Listings)**
- **URL:** https://www.imovirtual.com
- **Data:** Same structure as sale listings, filtered to rentals
- **Ingestion:** Same scraper as S05, filtered by operation_type = 'rent'
- **Volume:** ~20K-30K active rental listings
- **Refresh:** Weekly
- **Role:** Additional rental comps for yield calculation (supplements S04)

**S14 — RNAL (Alojamento Local Registry)**
- **URL:** https://rnt.turismodeportugal.pt
- **Data:** Licensed STR properties — address, license number, capacity, type, status
- **Format:** HTML (JS-rendered portal)
- **Ingestion:** Selenium → Bronze; or FOI request to Turismo de Portugal
- **Volume:** ~120K licenses nationally
- **Refresh:** Monthly
- **Role:** STR licensing feasibility; AL density per neighbourhood; matched with Inside Airbnb

**S20 — ARU Boundaries**
- **Source:** Municipal câmaras, DRE portal
- **Data:** Urban rehabilitation area polygons
- **Format:** Shapefile, PDF maps
- **Ingestion:** Download/digitize → PostGIS
- **Volume:** ~50-100 zones (major cities)
- **Refresh:** Ad-hoc (changes with municipal decisions)
- **Role:** Tax benefits for renovation (IMT exemption, reduced IMI, IRS deductions in ARU)

**S22 — InfoEscolas (School Quality)**
- **URL:** https://www.infoescolas.pt
- **Data:** School exam results, pass rates, socioeconomic context
- **Format:** HTML (JS-rendered)
- **Ingestion:** Selenium → Bronze → geocode via Nominatim
- **Volume:** ~8K schools
- **Refresh:** Annual (July after exam results)
- **Role:** Education quality score for property_location_scores; hedonic model feature

**S23 — SNS Healthcare Facilities**
- **URL:** https://www.sns.gov.pt + OSM
- **Data:** Hospitals, health centers (USF/UCSP), pharmacies
- **Format:** XLSX, OSM
- **Ingestion:** Download XLSX + supplement from OSM → geocode → Bronze
- **Volume:** ~5K facilities
- **Refresh:** Quarterly
- **Role:** Healthcare accessibility score for property_location_scores

**S24 — GTFS Transport Schedules**
- **URL:** Carris Metropolitana, CP, Metro Lisboa, Metro Porto, STCP
- **Data:** Stop locations, routes, frequencies, timetables
- **Format:** GTFS ZIP (standardized)
- **Ingestion:** Download ZIP → Python GTFS parser → PostGIS
- **Volume:** ~30K stops, ~500 routes
- **Refresh:** Quarterly
- **Role:** Transport frequency data to refine transport_score (complements S10 stop locations)

**S29 — INE Rental Price Index**
- **URL:** https://www.ine.pt (same API as S01)
- **Data:** Official median rents by municipality (new contracts)
- **Format:** JSON (API)
- **Ingestion:** REST API → Bronze (same pipeline as S01)
- **Volume:** ~10K records
- **Refresh:** Quarterly
- **Role:** Official rent benchmarks for yield validation

**S34 — Competitive Developments (Scraped)**
- **URL:** Idealista new-build filter, developer websites, SIR database
- **Data:** New-build projects — developer, unit count, pricing, absorption rate
- **Format:** Mixed (HTML scraping + manual data entry)
- **Ingestion:** Idealista new-build filter → Scrapy + manual enrichment → Bronze
- **Volume:** ~50-200 active projects (Lisbon + Porto metro areas)
- **Refresh:** Monthly
- **Role:** Competitive landscape for UC-2 pricing strategy

---

# Part II — Technology Stack & Architecture

---

## 3. Technology Stack

### 3.1 Primary Stack

| Component | Technology | Version | Rationale |
|---|---|---|---|
| **Core Database** | PostgreSQL + PostGIS | 16 + 3.4 | First-class spatial support, mature ecosystem. PostGIS is the industry standard for geospatial data warehousing. |
| **Object Storage** | MinIO (self-hosted) | latest | Raw file storage for PDFs, Shapefiles, HTML snapshots. S3-compatible and free. |
| **Transformation** | dbt Core | 1.7+ | SQL-based transformations with lineage, testing, documentation. Bronze→Silver→Gold. |
| **Orchestration** | Apache Airflow | 2.8+ | Battle-tested for complex DAGs with mixed task types (API calls, scraping, file processing, dbt runs). |
| **Analytical Engine** | DuckDB (supplement) | 0.10+ | Fast analytical queries on Parquet files alongside PostgreSQL for heavy OLAP scans. |
| **Geocoding** | Nominatim (self-hosted) | 4.4 | OSM-based, no API limits, GDPR-compliant. Essential for geocoding scraped addresses. |
| **Routing** | OSRM (self-hosted) | 5.27 | Drive-time isochrones and distance calculations. Load Portugal OSM extract. |
| **Scraping** | Scrapy + Selenium | 2.11 / 4.x | Web scraping (Scrapy) + JS-rendered sites (Selenium with headless Chromium). |
| **PDF Parsing** | tabula-py + camelot | latest | Extract tables from PDF reports (IMPIC, market reports). |
| **Spatial Python** | GeoPandas + Shapely | 0.14 / 2.0 | Geo ETL, spatial operations in Python. |
| **ML / Stats** | scikit-learn + statsmodels | latest | Hedonic regression model training and evaluation. |
| **Viz: BI** | Metabase | 0.48+ | Business dashboards — Investment Board and Pricing Board. |
| **Viz: Spatial** | QGIS + Kepler.gl | 3.34 / 2.5 | Spatial analysis and map visualization. |
| **Viz: Custom** | Streamlit | 1.30+ | Custom apps — property valuation tool, pricing simulator. |
| **API Serving** | PostgREST or FastAPI | latest | Internal data API for external tools. |
| **Data Quality** | dbt tests + Great Expectations | latest | Schema validation, freshness checks, anomaly detection. |
| **Language** | Python | 3.12 | Everything — scrapers, ETL, ML, utilities. |
| **Version Control** | Git + GitHub | — | All dbt models, Airflow DAGs, scraper code. |
| **Containerization** | Docker + Docker Compose | — | Reproducible dev environment. All services containerized. |

### 3.2 Alternative Cloud-Native Stack

| Component | Self-Hosted | Cloud Alternative |
|---|---|---|
| PostgreSQL + PostGIS | Docker / bare metal | AWS RDS PostgreSQL + PostGIS, or Google Cloud SQL |
| MinIO | Docker | AWS S3 |
| Airflow | Docker | AWS MWAA, GCP Cloud Composer, Astronomer |
| dbt Core | CLI | dbt Cloud |
| Metabase | Docker | Metabase Cloud, or Looker / Preset |
| Nominatim | Docker | Google Maps Geocoding API (pay per request) |
| OSRM | Docker | Google Distance Matrix API (pay per request) |

**Recommendation:** Start self-hosted on a single powerful server. The spatial workloads (PostGIS queries, OSRM routing, Nominatim geocoding) benefit enormously from local I/O and memory. Cloud egress costs add up fast with large GIS datasets.

---

## 4. Infrastructure & Deployment

### 4.1 Docker Compose Service Map

```yaml
# docker-compose.yml
services:
  # ── Core Database ──
  postgres:
    image: postgis/postgis:16-3.4
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: re_warehouse
      POSTGRES_USER: re_admin
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    shm_size: '4g'
    command: >
      postgres
        -c shared_buffers=8GB
        -c effective_cache_size=24GB
        -c work_mem=256MB
        -c maintenance_work_mem=2GB
        -c max_parallel_workers_per_gather=4

  # ── Object Storage ──
  minio:
    image: minio/minio
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"

  # ── Orchestration ──
  airflow-webserver:
    image: apache/airflow:2.8-python3.12
    depends_on:
      - postgres
    ports:
      - "8080:8080"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./plugins:/opt/airflow/plugins

  airflow-scheduler:
    image: apache/airflow:2.8-python3.12
    depends_on:
      - postgres

  airflow-worker:
    image: custom-airflow-worker  # Extended with Scrapy, Selenium, geopandas
    depends_on:
      - postgres
      - minio

  # ── Spatial Services ──
  nominatim:
    image: mediagis/nominatim:4.4
    volumes:
      - nominatim_data:/var/lib/postgresql/14/main
    environment:
      PBF_URL: https://download.geofabrik.de/europe/portugal-latest.osm.pbf

  osrm:
    image: osrm/osrm-backend
    volumes:
      - osrm_data:/data
    ports:
      - "5001:5000"
    command: osrm-routed --algorithm mld /data/portugal-latest.osrm

  # ── Visualization ──
  metabase:
    image: metabase/metabase
    depends_on:
      - postgres
    ports:
      - "3000:3000"

  # ── Headless Browser ──
  selenium:
    image: selenium/standalone-chromium
    ports:
      - "4444:4444"
    shm_size: '2g'
```

### 4.2 Server Specification

| Component | Spec |
|---|---|
| **Server** | Hetzner AX102 (or equivalent) |
| **CPU** | AMD Ryzen 9 7950X (16 cores / 32 threads) |
| **RAM** | 128 GB DDR5 |
| **Storage** | 2 × 2TB NVMe SSD |
| **Cost** | ~€85/month |

### 4.3 PostgreSQL Schema Organization

```sql
-- Bronze: Raw ingested data (one schema per domain)
CREATE SCHEMA bronze_ine;
CREATE SCHEMA bronze_listings;
CREATE SCHEMA bronze_geo;
-- S12 Census 2021 (BGRI GeoPackage) stored in bronze_ine (same publisher, INE).
CREATE SCHEMA bronze_tourism;
CREATE SCHEMA bronze_macro;
CREATE SCHEMA bronze_regulatory;
CREATE SCHEMA bronze_location;

-- Silver: Cleaned, conformed, geocoded
CREATE SCHEMA silver_properties;
CREATE SCHEMA silver_geo;
CREATE SCHEMA silver_market;
CREATE SCHEMA silver_location;
CREATE SCHEMA silver_ref;

-- Gold: Analytical models, facts, dimensions
CREATE SCHEMA gold_analytics;
CREATE SCHEMA gold_reporting;

-- Support
CREATE SCHEMA staging;
CREATE SCHEMA metadata;
```

**Note:** Compared to the full blueprint, the following bronze schemas are removed: `bronze_energy` (S13 ADENE deferred), `bronze_market` (S33 Google Trends and S32 PORDATA deferred). The `bronze_ref` schema is merged into `silver_ref` since the reference tables (renovation costs, IMT/IMI) are manually seeded rather than ingested from external sources.

---

## 5. Conceptual Architecture (Medallion Pattern)

### 5.1 End-to-End Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES (24 — MVP)                        │
│                                                                             │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────────┐ │
│  │ REST APIs│ │ Web Scrape│ │ File     │ │ GIS     │ │ Commercial      │ │
│  │          │ │           │ │ Downloads│ │ Services│ │ Feeds           │ │
│  │ INE      │ │ Imovirtual│ │ CAOP SHP │ │ ArcGIS │ │ Conf.Imobiliário│ │
│  │ BPStat   │ │ RNAL      │ │ OSM PBF  │ │ REST   │ │                 │ │
│  │ Eurostat │ │ InfoEscola│ │ GTFS ZIP │ │        │ │                 │ │
│  │ ECB      │ │ Comp.Devs │ │ Census   │ │        │ │                 │ │
│  │ Idealista│ │           │ │ InsideAir│ │        │ │                 │ │
│  └─────┬────┘ └─────┬─────┘ └─────┬────┘ └────┬───┘ └────────┬───────┘ │
│        │            │             │            │              │          │
└────────┼────────────┼─────────────┼────────────┼──────────────┼──────────┘
         │            │             │            │              │
         ▼            ▼             ▼            ▼              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER (Airflow)                            │
│                                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ API Pullers  │ │ Web Scrapers │ │ File Loaders │ │ GIS Importers   │  │
│  │ (requests,   │ │ (Scrapy,     │ │ (wget, curl, │ │ (ogr2ogr,       │  │
│  │  aiohttp,    │ │  Selenium)   │ │  gunzip,     │ │  osm2pgsql)     │  │
│  │  pandasdmx)  │ │              │ │  tabula-py)  │ │                 │  │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬────────┘  │
│         │                │                │                   │           │
│         ▼                ▼                ▼                   ▼           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  Raw File Landing Zone: MinIO (S3-compatible)                      │  │
│  │  s3://raw/{source}/{year}/{month}/{filename}                       │  │
│  │  HTML snapshots, Shapefiles, PBF, CSV originals                    │  │
│  └─────────────────────────────┬───────────────────────────────────────┘  │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BRONZE LAYER (PostgreSQL + PostGIS)                       │
│                    Raw, append-only, source-faithful                         │
│                                                                             │
│  ┌──────────────────────┐ ┌────────────────┐ ┌──────────────────────┐      │
│  │ bronze_ine           │ │ bronze_listings│ │ bronze_geo           │      │
│  │ .raw_indicators      │ │ .raw_idealista │ │ .raw_caop_freguesias │      │
│  │ .raw_bgri            │ │ .raw_imovirt.  │ │ .raw_caop_municipios │      │
│  │                      │ │ .raw_comp_devs │ │ .raw_caop_distritos  │      │
│  └──────────────────────┘ └────────────────┘ │ .raw_aru_zones       │      │
│  ┌────────────────┐ ┌────────────────┐       └──────────────────────┘      │
│  │ bronze_macro   │ │ bronze_tourism │       ┌──────────────────────┐      │
│  │ .raw_bpstat    │ │ .raw_rnal      │       │ bronze_location       │      │
│  │ .raw_eurostat  │ │ .raw_insideab  │       │ .raw_osm_* (18 tbls) │      │
│  │ .raw_ecb       │ └────────────────┘       │ .raw_schools          │      │
│  └────────────────┘                          │ .raw_healthcare       │      │
│  ┌──────────────────┐                        └──────────────────────┘      │
│  │ .raw_pdm_zones   │                                                      │
│  └──────────────────┘                                                      │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                            dbt models
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SILVER LAYER (PostgreSQL + PostGIS)                       │
│                    Cleaned, conformed, geocoded, deduplicated                │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐ │
│  │ silver_properties    │  │ silver_geo           │  │ silver_location   │ │
│  │ .unified_listings    │  │ .census_demographics │  │ .transport_stops  │ │
│  │ .listing_price_hist  │  │ .zoning              │  │ .schools          │ │
│  │ .listing_matches     │  └──────────────────────┘  │ .healthcare_fac   │ │
│  └──────────────────────┘                            │ .osm_pois         │ │
│  ┌──────────────────────┐  ┌──────────────────────┐  └───────────────────┘ │
│  │ silver_market        │  │ silver_ref           │                        │
│  │ .macro_timeseries    │  │ .renovation_costs    │                        │
│  │ .str_registry        │  │ .imt_brackets        │                        │
│  └──────────────────────┘  │ .imi_rates           │                        │
│                            │ .unit_premiums       │                        │
│                            └──────────────────────┘                        │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                            dbt models
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GOLD LAYER (PostgreSQL + PostGIS)                         │
│                    Analytical models, facts, dimensions, scores              │
│                                                                             │
│  SHARED DIMENSIONS:                                                         │
│  ┌──────────────┐ ┌──────────────────┐ ┌──────────────────┐                │
│  │ dim_geography│ │ dim_time         │ │ dim_property_type│                │
│  └──────────────┘ └──────────────────┘ └──────────────────┘                │
│                                                                             │
│  FACT TABLES:                                                               │
│  ┌─────────────────────┐ ┌──────────────────────┐ ┌───────────────────┐    │
│  │ fact_transactions   │ │ fact_listings_snapshot│ │ fact_str_market   │    │
│  └─────────────────────┘ └──────────────────────┘ └───────────────────┘    │
│                                                                             │
│  SHARED ANALYTICAL:                                                         │
│  ┌────────────────────────────┐  ┌───────────────────────────┐             │
│  │ hedonic_features           │  │ property_location_scores  │             │
│  └──────────┬─────────────────┘  └──────────┬────────────────┘             │
│             ▼                               ▼                              │
│  ┌────────────────────────────┐  ┌───────────────────────────┐             │
│  │ property_comparables       │  │ neighbourhood_market_stats│             │
│  └──────────┬─────────────────┘  └──────────┬────────────────┘             │
│             │                               │                              │
│  ┌──────────┴───────────────────────────────┴──────────────────────┐       │
│  │                                                                 │       │
│  │  ┌─────────────────────────────────────────────────────────┐    │       │
│  │  │  UC-1: INVESTMENT ANALYSIS                              │    │       │
│  │  │                                                         │    │       │
│  │  │  property_valuation ──── hedonic gap + comp gap         │    │       │
│  │  │  investment_yield_analysis ── LTR + STR + leveraged     │    │       │
│  │  │  renovation_opportunity ──── cost + ROI + ARU benefits  │    │       │
│  │  │  neighbourhood_trajectory ── momentum + catalysts       │    │       │
│  │  │  area_catalysts ──── infrastructure + regulatory        │    │       │
│  │  │          │                                              │    │       │
│  │  │          ▼                                              │    │       │
│  │  │  ┌────────────────────────────────────────────────┐     │    │       │
│  │  │  │  investment_opportunities (materialized view)  │     │    │       │
│  │  │  │  Composite investment_score per property       │     │    │       │
│  │  │  └────────────────────────────────────────────────┘     │    │       │
│  │  └─────────────────────────────────────────────────────────┘    │       │
│  │                                                                 │       │
│  │  ┌─────────────────────────────────────────────────────────┐    │       │
│  │  │  UC-2: PRICING STRATEGY                                 │    │       │
│  │  │                                                         │    │       │
│  │  │  development_projects ──── project-level definition     │    │       │
│  │  │  development_units ──── unit-level attributes           │    │       │
│  │  │  competitive_developments ──── competing supply         │    │       │
│  │  │  absorption_rate_model ──── time-to-sell by segment     │    │       │
│  │  │  location_price_premiums ──── hedonic coefficients      │    │       │
│  │  │  (silver_ref.unit_premiums) ── floor/view/orient €/sqm  │    │       │
│  │  │          │                                              │    │       │
│  │  │          ▼                                              │    │       │
│  │  │  ┌────────────────────────────────────────────────┐     │    │       │
│  │  │  │  unit_pricing_recommendation (per unit)        │     │    │       │
│  │  │  │  project_pricing_summary (materialized view)   │     │    │       │
│  │  │  └────────────────────────────────────────────────┘     │    │       │
│  │  └─────────────────────────────────────────────────────────┘    │       │
│  └─────────────────────────────────────────────────────────────────┘       │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SERVING LAYER                                             │
│                                                                             │
│  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐  │
│  │ Metabase           │  │ Streamlit Apps      │  │ PostgREST / FastAPI │  │
│  │ Investment board    │  │ Property valuation  │  │ Internal data API   │  │
│  │ Pricing dashboard  │  │ Pricing simulator   │  │ for external tools  │  │
│  └────────────────────┘  └────────────────────┘  └──────────────────────┘  │
│  ┌────────────────────┐  ┌────────────────────┐                            │
│  │ QGIS / Kepler.gl   │  │ Jupyter Notebooks  │                            │
│  │ Spatial analysis   │  │ Hedonic model       │                            │
│  │ Map visualisation  │  │ training & eval     │                            │
│  └────────────────────┘  └────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Flows by Source Type

### Flow A: REST API Sources (INE, BPStat, Eurostat, ECB, Idealista)
```
Airflow DAG (scheduled) → Python operator (requests/pandasdmx)
  → API response (JSON/CSV)
    → Validate response schema
      → Insert into Bronze table (append-only)
        → dbt staging model (type casting, null handling)
          → dbt Silver model (conform to dimensions)
            → dbt Gold model (metrics, facts)
```

### Flow B: Web Scraping Sources (Imovirtual, RNAL, InfoEscolas, Competitive Devs)
```
Airflow DAG (scheduled) → Scrapy/Selenium operator
  → Raw HTML pages
    → Store HTML snapshot in MinIO (s3://raw/...)
      → Parse HTML → structured records
        → Insert into Bronze table
          → Geocode addresses via Nominatim
            → dbt Silver model (deduplicate, conform)
              → dbt Gold model
```

### Flow C: GIS Sources (CAOP, OSM, PDM, ARU)
```
Airflow DAG (triggered) → Download file (wget/curl)
  → Store raw file in MinIO
    → Import via ogr2ogr/osm2pgsql into Bronze PostGIS table
      → dbt Silver model (reproject, clean, index)
        → Spatial joins for enrichment
```

### Flow D: Derived Computation (Location Scores, Valuations)
```
Airflow DAG (post-ingestion) → dbt run
  → silver_properties.unified_listings
    + silver_location.* (transport, schools, healthcare, POIs)
      → Spatial proximity queries (PostGIS ST_DWithin)
        → gold_analytics.property_location_scores
          → gold_analytics.hedonic_features
            → Python/SQL hedonic model scoring
              → gold_analytics.property_valuation
                → gold_reporting.investment_opportunities
```

---

## 7. Conceptual Data Models

### 7.1 Entity-Relationship Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         CORE ENTITIES                                    │
│                                                                          │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐    │
│  │  GEOGRAPHY   │ 1     * │  PROPERTY    │ 1     * │  PRICE       │    │
│  │  (freguesia) ├─────────┤  (listing)   ├─────────┤  HISTORY     │    │
│  └──────┬───────┘         └──────┬───────┘         └──────────────┘    │
│         │                        │                                      │
│         │                        │ has                                   │
│  ┌──────┴───────┐        ┌──────┴───────┐                              │
│  │  CENSUS      │        │  LOCATION    │                              │
│  │  DEMOGRAPHICS│        │  SCORE       │                              │
│  └──────────────┘        └──────────────┘                              │
│                                                                          │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐    │
│  │  TRANSPORT   │         │  SCHOOL      │         │  HEALTHCARE  │    │
│  │  STOP        │         │              │         │  FACILITY    │    │
│  └──────────────┘         └──────────────┘         └──────────────┘    │
│                                                                          │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐    │
│  │  ZONING      │         │  ARU ZONE    │         │  MACRO       │    │
│  │  (PDM)       │         │              │         │  INDICATOR   │    │
│  └──────────────┘         └──────────────┘         └──────────────┘    │
│                                                                          │
│  ┌──────────────┐         ┌──────────────┐                              │
│  │  STR         │         │  AMENITY     │                              │
│  │  REGISTRY    │         │  (POI)       │                              │
│  └──────────────┘         └──────────────┘                              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 7.2 UC-1 Conceptual Model: Investment Analysis

```
                    ┌─────────────────────┐
                    │     PROPERTY        │
                    │   (unified listing) │
                    └──────────┬──────────┘
                               │
              has              │              has
    ┌─────────────────┐        │        ┌────────────────┐
    │  VALUATION      │        │        │  LOCATION      │
    │                 │        │        │  SCORE         │
    │ predicted_price │◄───────┤────────►               │
    │ asking_price    │        │        │ transport      │
    │ hedonic_gap_%   │        │        │ walkability    │
    │ comp_gap_%      │        │        │ education      │
    │ blended_gap     │        │        │ healthcare     │
    │ signal          │        │        │ overall        │
    └─────────────────┘        │        └────────────────┘
                               │
    ┌─────────────────┐        │        ┌────────────────┐
    │  YIELD          │        │        │  RENOVATION    │
    │  ANALYSIS       │        │        │  OPPORTUNITY   │
    │                 │◄───────┤────────►               │
    │ gross_yield     │        │        │ reno_cost      │
    │ net_yield       │        │        │ post_reno_val  │
    │ STR_yield       │        │        │ ROI            │
    │ cash_on_cash    │        │        │ is_ARU         │
    │ 5y_total_return │        │        │ tier           │
    └─────────────────┘        │        └────────────────┘
                               │
         is located in         │
    ┌─────────────────┐        │        ┌────────────────┐
    │ NEIGHBOURHOOD   │        │        │  CATALYST      │
    │ TRAJECTORY      │◄───────┘────────►               │
    │                 │                 │ type (metro,   │
    │ price_momentum  │                 │  ARU, school)  │
    │ supply_demand   │  near           │ name           │
    │ demographics    │◄────────────────│ completion_dt  │
    │ trajectory_score│                 │ impact_%       │
    │ label           │                 │ impact_radius  │
    └─────────────────┘                 └────────────────┘
            │
            ▼
    ┌─────────────────────────────────────┐
    │      INVESTMENT OPPORTUNITY         │
    │     (composite scoring view)        │
    │                                     │
    │  investment_score (0-100)           │
    │  = f(valuation_gap, yield,          │
    │      renovation_roi, trajectory,    │
    │      catalysts, listing_freshness)  │
    └─────────────────────────────────────┘
```

### 7.3 UC-2 Conceptual Model: Pricing Strategy

```
    ┌──────────────────┐         ┌──────────────────┐
    │  DEVELOPMENT     │ 1     * │  UNIT            │
    │  PROJECT         ├─────────┤                  │
    │                  │         │  typology        │
    │  name            │         │  area_m2         │
    │  location        │         │  floor           │
    │  total_units     │         │  orientation     │
    │  total_cost      │         │  view_type       │
    │  target_margin   │         │  has_parking     │
    │                  │         │  status          │
    └────────┬─────────┘         └────────┬─────────┘
             │                            │
    competes │                    priced   │
      with   │                     by     │
             ▼                            ▼
    ┌──────────────────┐         ┌──────────────────┐
    │  COMPETITIVE     │         │  PRICING         │
    │  DEVELOPMENT     │         │  RECOMMENDATION  │
    │                  │         │                  │
    │  project_name    │         │  base_price_sqm  │
    │  developer       │  used   │  + floor_prem    │
    │  avg_price_sqm   │──in──►  │  + view_prem     │
    │  units_available │         │  + orient_prem   │
    │  absorption_rate │         │  + terrace_prem  │
    └──────────────────┘         │  = rec_price_sqm │
                                 │  rec_price_eur   │
    ┌──────────────────┐         │  margin_%        │
    │  ABSORPTION      │         │  days_to_sell    │
    │  RATE MODEL      │ used    │  confidence      │
    │                  │──in──►  └──────────────────┘
    │  typology        │                  │
    │  price_segment   │                  │
    │  days_on_market  │         aggregates
    │  %_sold_30/60/90d│                  │
    └──────────────────┘                  ▼
                                 ┌──────────────────┐
    ┌──────────────────┐         │  PROJECT PRICING │
    │  LOCATION PRICE  │         │  SUMMARY         │
    │  PREMIUMS        │         │                  │
    │                  │ used    │  total_revenue   │
    │  feature_name    │──in──►  │  blended_margin  │
    │  coefficient_eur │  all    │  by_typology     │
    │  coefficient_%   │ models  │  vs_competition  │
    │  scope (LX/Porto)│         │  absorption_fcst │
    └──────────────────┘         └──────────────────┘
```

### 7.4 Star Schema Overview

```
                           ┌──────────────────┐
                           │   dim_time       │
                           │                  │
                           │  date_key (PK)   │
                           │  year, quarter   │
                           │  month           │
                           └────────┬─────────┘
                                    │
┌──────────────────┐    ┌───────────┴──────────────┐    ┌──────────────────┐
│ dim_geography    │    │  fact_transactions       │    │dim_property_type │
│                  │    │                          │    │                  │
│  geo_key (PK)    ├────┤  transaction_key (PK)    ├────┤  prop_type_key   │
│  distrito        │    │  date_key (FK)           │    │  (PK)            │
│  concelho        │    │  geo_key (FK)            │    │  category        │
│  freguesia       │    │  property_type_key (FK)  │    │  subcategory     │
│  boundary (geom) │    │  median_price_sqm        │    │  typology        │
│  centroid        │    │  transaction_count       │    │  condition       │
│  population      │    │  yoy_change_%            │    └──────────────────┘
│  area_km2        │    └──────────────────────────┘
└────────┬─────────┘
         │
         │          ┌──────────────────────────────┐
         │          │  fact_listings_snapshot       │
         ├──────────┤                              │
         │          │  snapshot_date                │
         │          │  geo_key (FK)                 │
         │          │  operation_type               │
         │          │  active_count                 │
         │          │  median_price_sqm             │
         │          │  avg_listing_age_days         │
         │          └──────────────────────────────┘
         │
         │          ┌──────────────────────────────┐
         │          │  fact_str_market              │
         └──────────┤                              │
                    │  snapshot_date                │
                    │  total_licensed_al            │
                    │  al_pct_of_housing            │
                    │  median_nightly_rate          │
                    │  estimated_revpar             │
                    └──────────────────────────────┘
```

---

# Part III — Physical Data Models

---

## 8. Physical Data Models — All Layers

### 8.1 Gold Layer — Shared Dimensions

#### dim_geography

The backbone dimension — every property, transaction, and metric ties back to geography.

```sql
CREATE TABLE gold_analytics.dim_geography (
    geo_key              SERIAL PRIMARY KEY,

    -- Administrative hierarchy (INE codes)
    distrito_code        CHAR(2) NOT NULL,           -- e.g., '11' = Lisboa
    distrito_name        VARCHAR(50) NOT NULL,
    concelho_code        CHAR(4) NOT NULL,            -- e.g., '1106' = Lisboa
    concelho_name        VARCHAR(100) NOT NULL,
    freguesia_code       CHAR(6) NOT NULL,            -- e.g., '110633' = Misericórdia
    freguesia_name       VARCHAR(150) NOT NULL,
    nut_i                VARCHAR(20),                  -- 'Continente'
    nut_ii               VARCHAR(50),                  -- 'Área Metropolitana de Lisboa'
    nut_iii              VARCHAR(50),

    -- Postal code zone
    postal_code_4        CHAR(4),

    -- Spatial (dual projections)
    freguesia_geom       GEOMETRY(MULTIPOLYGON, 4326), -- WGS84 boundary (display)
    freguesia_geom_pt    GEOMETRY(MULTIPOLYGON, 3763), -- PT-TM06 boundary (metric distance queries)
    centroid             GEOMETRY(POINT, 4326),
    area_km2             NUMERIC(10,3),

    -- Census 2021 key metrics (denormalized for convenience)
    population_2021      INTEGER,
    households_2021      INTEGER,
    pop_density_km2      NUMERIC(10,2),
    median_age           NUMERIC(4,1),
    foreign_resident_pct NUMERIC(5,2),

    -- Metadata
    source_caop_year     INTEGER,
    valid_from           DATE,
    valid_to             DATE,
    is_current           BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_geo_freguesia ON gold_analytics.dim_geography(freguesia_code);
CREATE INDEX idx_geo_concelho ON gold_analytics.dim_geography(concelho_code);
CREATE INDEX idx_geo_geom ON gold_analytics.dim_geography USING GIST(freguesia_geom);
CREATE INDEX idx_geo_geom_pt ON gold_analytics.dim_geography USING GIST(freguesia_geom_pt);
```

#### dim_time

```sql
CREATE TABLE gold_analytics.dim_time (
    date_key             INTEGER PRIMARY KEY,          -- YYYYMMDD
    full_date            DATE NOT NULL,
    year                 SMALLINT NOT NULL,
    quarter              SMALLINT NOT NULL,
    month                SMALLINT NOT NULL,
    month_name           VARCHAR(20),
    week_of_year         SMALLINT,
    day_of_month         SMALLINT,
    day_of_week          SMALLINT,
    is_weekend           BOOLEAN,
    fiscal_quarter       SMALLINT,
    ine_quarter_label    VARCHAR(10)                   -- e.g., '2024Q3' for INE alignment
);
```

#### dim_property_type

```sql
CREATE TABLE gold_analytics.dim_property_type (
    property_type_key    SERIAL PRIMARY KEY,
    category             VARCHAR(30) NOT NULL,         -- 'residential', 'commercial', 'land'
    subcategory          VARCHAR(50),                  -- 'apartment', 'villa', 'townhouse'
    typology             VARCHAR(10),                  -- 'T0', 'T1', 'T2', 'T3', 'T4', 'T5+'
    condition            VARCHAR(30),                  -- 'new', 'renovated', 'good', 'used', 'to_renovate'
    ine_category_code    VARCHAR(10),
    description_pt       VARCHAR(100),
    description_en       VARCHAR(100)
);
```

### 8.2 Bronze Layer — Raw Ingested Data

#### Listings (S03/S04 Idealista, S05/S06 Imovirtual)

```sql
CREATE TABLE bronze_listings.raw_idealista (
    id                   BIGSERIAL PRIMARY KEY,
    source_listing_id    VARCHAR(50) NOT NULL,
    listing_url          TEXT,
    operation_type       VARCHAR(10),                  -- 'sale', 'rent'
    price                NUMERIC(12,2),
    currency             CHAR(3) DEFAULT 'EUR',
    property_type_raw    VARCHAR(100),
    typology_raw         VARCHAR(20),
    useful_area_m2       NUMERIC(10,2),
    gross_area_m2        NUMERIC(10,2),
    plot_area_m2         NUMERIC(12,2),
    num_rooms            SMALLINT,
    num_bathrooms        SMALLINT,
    floor_number         SMALLINT,
    has_elevator         BOOLEAN,
    has_parking          BOOLEAN,
    has_terrace          BOOLEAN,
    has_garden           BOOLEAN,
    has_pool             BOOLEAN,
    energy_class         CHAR(2),
    construction_year    SMALLINT,
    condition_raw        VARCHAR(50),
    description_text     TEXT,
    address_raw          TEXT,
    district_raw         VARCHAR(100),
    municipality_raw     VARCHAR(100),
    parish_raw           VARCHAR(100),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    listing_date         DATE,
    update_date          DATE,
    agent_name           VARCHAR(200),
    agent_type           VARCHAR(50),

    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'idealista',
    _scrape_date         DATE NOT NULL,
    _batch_id            VARCHAR(50),
    _raw_html_path       TEXT
);
CREATE INDEX idx_idealista_lid ON bronze_listings.raw_idealista(source_listing_id);
CREATE INDEX idx_idealista_dt ON bronze_listings.raw_idealista(_scrape_date);

-- Identical structure for:
-- bronze_listings.raw_imovirtual (S05/S06)
```

#### INE — Indicators + Census BGRI (S01/S12/S29)

Both INE data sources land in `bronze_ine`: the API indicators (33 statistical series)
and the BGRI census GeoPackage (203,264 statistical subsections).

```sql
-- ── raw_indicators: INE API (S01/S29) ──────────────────────────────────────
-- 33 indicators, 907,533 rows. One row per (indicator × period × geography × dimensions).
-- Schema derived from actual API response — INE JSON nests observations
-- inside Dados[period] arrays with variable dimension columns (dim_3..dim_5).

CREATE TABLE bronze_ine.raw_indicators (
    id                   BIGSERIAL PRIMARY KEY,

    -- Indicator identity
    indicator_code       VARCHAR(20) NOT NULL,            -- IndicadorCod (e.g. '0009201')
    indicator_name       TEXT,                            -- IndicadorDsg (full description)
    last_updated         DATE,                            -- DataUltimoAtualizacao from INE

    -- Period (key from Dados dict — free-text, not standardised)
    time_period          VARCHAR(50) NOT NULL,            -- e.g. '1st Quarter 2009', 'April 2007', '2024'

    -- Geography
    geocod               VARCHAR(20),                    -- INE geographic code (e.g. 'PT', '1106', '11E')
    geodsg               VARCHAR(200),                   -- Geographic name (e.g. 'Portugal', 'Lisboa')

    -- Dimensions (variable per indicator — up to 3)
    dim_3                VARCHAR(20),                    -- Dimension 3 code (e.g. 'H11')
    dim_3_t              VARCHAR(200),                   -- Dimension 3 label (e.g. 'New')
    dim_4                VARCHAR(20),                    -- Dimension 4 code (some indicators only)
    dim_4_t              VARCHAR(200),                   -- Dimension 4 label
    dim_5                VARCHAR(20),                    -- Dimension 5 code (rare — e.g. interest rates)
    dim_5_t              VARCHAR(200),                   -- Dimension 5 label

    -- Values
    valor                NUMERIC(15,4),                  -- Parsed numeric value (NULL when missing/convention code)
    ind_string           VARCHAR(50),                    -- Raw formatted string (e.g. '104,55', 'x', '...')
    sinal_conv           VARCHAR(10),                    -- Convention code (e.g. 'x' = not available)
    sinal_conv_desc      VARCHAR(100),                   -- Convention description (e.g. 'Not available')

    -- Metadata
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(50) DEFAULT 'ine_api',
    _batch_id            VARCHAR(50),
    _api_extraction_ts   TIMESTAMPTZ                     -- DataExtracao from INE response
);
CREATE INDEX idx_ine_ind_code ON bronze_ine.raw_indicators(indicator_code);
CREATE INDEX idx_ine_ind_period ON bronze_ine.raw_indicators(indicator_code, time_period);
CREATE INDEX idx_ine_ind_geo ON bronze_ine.raw_indicators(indicator_code, geocod);

-- ── raw_bgri: Census 2021 BGRI GeoPackage (S12) ───────────────────────────
-- Source: BGRI21_CONT.gpkg from mapas.ine.pt (480.8 MB).
-- Single layer BGRI21_CONT — 203,264 statistical subsections.
-- Wide-format: one row per polygon, 32 census columns + geometry.
-- Column names match the GeoPackage exactly (lowercase in PostGIS).

CREATE TABLE bronze_ine.raw_bgri (
    objectid                 INTEGER,
    bgri2021                 VARCHAR(20) NOT NULL,           -- Statistical subsection code (11-char)
    dt21                     VARCHAR(2),                     -- District code
    dtmn21                   VARCHAR(4),                     -- Municipality code
    dtmnfr21                 VARCHAR(6),                     -- Parish code (DICOFRE)
    dtmnfrsec21              VARCHAR(10),                    -- Section code
    secnum21                 VARCHAR(4),                     -- Section number within parish
    ssnum21                  VARCHAR(4),                     -- Subsection number within section
    secssnum21               VARCHAR(8),                     -- Section + subsection combined
    subseccao                VARCHAR(20),                    -- Subsection label
    nuts1                    VARCHAR(50),
    nuts2                    VARCHAR(50),
    nuts3                    VARCHAR(50),

    -- Buildings (12)
    n_edificios_classicos                              DOUBLE PRECISION,
    n_edificios_class_const_1_ou_2_aloj                DOUBLE PRECISION,
    n_edificios_class_const_3_ou_mais_alojamentos      DOUBLE PRECISION,
    n_edificios_exclusiv_resid                         DOUBLE PRECISION,
    n_edificios_1_ou_2_pisos                           DOUBLE PRECISION,
    n_edificios_3_ou_mais_pisos                        DOUBLE PRECISION,
    n_edificios_constr_antes_1945                       DOUBLE PRECISION,
    n_edificios_constr_1946_1980                        DOUBLE PRECISION,
    n_edificios_constr_1981_2000                        DOUBLE PRECISION,
    n_edificios_constr_2001_2010                        DOUBLE PRECISION,
    n_edificios_constr_2011_2021                        DOUBLE PRECISION,
    n_edificios_com_necessidades_reparacao              DOUBLE PRECISION,

    -- Dwellings (8)
    n_alojamentos_total                                DOUBLE PRECISION,
    n_alojamentos_familiares                           DOUBLE PRECISION,
    n_alojamentos_fam_class_rhabitual                  DOUBLE PRECISION,
    n_alojamentos_fam_class_vagos_ou_resid_secundaria  DOUBLE PRECISION,
    n_rhabitual_acessivel_cadeiras_rodas               DOUBLE PRECISION,
    n_rhabitual_com_estacionamento                     DOUBLE PRECISION,
    n_rhabitual_prop_ocup                              DOUBLE PRECISION,
    n_rhabitual_arrendados                             DOUBLE PRECISION,

    -- Households (5)
    n_agregados_domesticos_privados                    DOUBLE PRECISION,
    n_adp_1_ou_2_pessoas                               DOUBLE PRECISION,
    n_adp_3_ou_mais_pessoas                            DOUBLE PRECISION,
    n_nucleos_familiares                               DOUBLE PRECISION,
    n_nucleos_familiares_com_filhos_tendo_o_mais_novo_menos_de_25  DOUBLE PRECISION,

    -- Population (7)
    n_individuos                                       DOUBLE PRECISION,
    n_individuos_h                                     DOUBLE PRECISION,
    n_individuos_m                                     DOUBLE PRECISION,
    n_individuos_0_14                                   DOUBLE PRECISION,
    n_individuos_15_24                                  DOUBLE PRECISION,
    n_individuos_25_64                                  DOUBLE PRECISION,
    n_individuos_65_ou_mais                             DOUBLE PRECISION,

    -- Shape metrics (from GPKG)
    shape_length             DOUBLE PRECISION,
    shape_area               DOUBLE PRECISION,

    -- Geometry
    geom                     GEOMETRY(MULTIPOLYGON, 3763),  -- ETRS89 / PT-TM06

    -- Metadata
    _load_timestamp          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_bgri_bgri2021 ON bronze_ine.raw_bgri(bgri2021);
CREATE INDEX idx_bgri_dtmnfr ON bronze_ine.raw_bgri(dtmnfr21);
CREATE INDEX idx_bgri_geom ON bronze_ine.raw_bgri USING GIST(geom);
```

#### CAOP Boundaries (S08)

Source is the CAOP GeoPackage from DGT. Three administrative boundary layers
loaded source-faithful into `bronze_geo`. CRS is EPSG:3763 (PT-TM06).

```sql
CREATE TABLE bronze_geo.raw_caop_freguesias (
    dtmnfr               VARCHAR(6) NOT NULL,           -- DICOFRE code (distrito 2 + municipio 2 + freguesia 2)
    freguesia            TEXT,
    municipio            TEXT,
    distrito_ilha        TEXT,
    nuts3_cod            VARCHAR(10),
    nuts3                TEXT,
    nuts2                TEXT,
    nuts1                TEXT,
    area_ha              DOUBLE PRECISION,
    perimetro_km         INTEGER,
    designacao_simplificada TEXT,
    geom                 GEOMETRY(MULTIPOLYGON, 3763),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_caop_freg_dtmnfr ON bronze_geo.raw_caop_freguesias(dtmnfr);
CREATE INDEX idx_caop_freg_geom ON bronze_geo.raw_caop_freguesias USING GIST(geom);

CREATE TABLE bronze_geo.raw_caop_municipios (
    dtmn                 VARCHAR(4) NOT NULL,            -- Distrito + Municipio code
    municipio            TEXT,
    distrito_ilha        TEXT,
    nuts3_cod            VARCHAR(10),
    nuts3                TEXT,
    nuts2                TEXT,
    nuts1                TEXT,
    area_ha              DOUBLE PRECISION,
    perimetro_km         INTEGER,
    n_freguesias         INTEGER,
    geom                 GEOMETRY(MULTIPOLYGON, 3763),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_caop_mun_geom ON bronze_geo.raw_caop_municipios USING GIST(geom);

CREATE TABLE bronze_geo.raw_caop_distritos (
    dt                   VARCHAR(2) NOT NULL,            -- Distrito code
    distrito             TEXT,
    nuts1_cod            VARCHAR(10),
    nuts1                TEXT,
    area_ha              DOUBLE PRECISION,
    perimetro_km         INTEGER,
    n_municipios         INTEGER,
    n_freguesias         DOUBLE PRECISION,
    geom                 GEOMETRY(MULTIPOLYGON, 3763),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_caop_dist_geom ON bronze_geo.raw_caop_distritos USING GIST(geom);
```

#### Macro Sources (S16 BPStat, S17 ECB, S18 Eurostat)

```sql
CREATE TABLE bronze_macro.raw_bpstat (
    id                   BIGSERIAL PRIMARY KEY,
    series_id            VARCHAR(50) NOT NULL,
    series_name          VARCHAR(500),
    period               VARCHAR(20),
    value                NUMERIC(20,6),
    unit                 VARCHAR(100),
    dimension_code       VARCHAR(50),
    dimension_value      VARCHAR(200),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'bpstat'
);

CREATE TABLE bronze_macro.raw_ecb (
    id                   BIGSERIAL PRIMARY KEY,
    series_key           VARCHAR(100) NOT NULL,
    series_name          VARCHAR(500),
    observation_date     DATE NOT NULL,
    value                NUMERIC(10,6),
    unit                 VARCHAR(50),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'ecb_sdw'
);

CREATE TABLE bronze_macro.raw_eurostat (
    id                   BIGSERIAL PRIMARY KEY,
    dataset_code         VARCHAR(30) NOT NULL,
    geo                  VARCHAR(10),
    time_period          VARCHAR(20),
    indicator            VARCHAR(50),
    value                NUMERIC(20,6),
    unit                 VARCHAR(50),
    flag                 VARCHAR(10),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'eurostat'
);
```

#### Tourism & STR (S14 RNAL, S15 Inside Airbnb)

```sql
CREATE TABLE bronze_tourism.raw_rnal (
    id                   BIGSERIAL PRIMARY KEY,
    rnal_number          VARCHAR(30),
    establishment_name   VARCHAR(300),
    establishment_type   VARCHAR(50),
    capacity_guests      SMALLINT,
    capacity_rooms       SMALLINT,
    address_raw          TEXT,
    municipality_raw     VARCHAR(100),
    freguesia_raw        VARCHAR(100),
    postal_code          VARCHAR(10),
    owner_name           VARCHAR(200),
    registration_date    DATE,
    status               VARCHAR(30),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'rnal',
    _scrape_date         DATE
);

CREATE TABLE bronze_tourism.raw_insideairbnb (
    id                   BIGSERIAL PRIMARY KEY,
    airbnb_listing_id    BIGINT,
    listing_name         TEXT,
    host_id              BIGINT,
    neighbourhood        VARCHAR(100),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    room_type            VARCHAR(50),
    price_usd            NUMERIC(10,2),
    minimum_nights       SMALLINT,
    number_of_reviews    INTEGER,
    last_review_date     DATE,
    reviews_per_month    NUMERIC(6,2),
    availability_365     SMALLINT,
    license_number       VARCHAR(50),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _data_date           DATE,
    _city                VARCHAR(30)
);
```

#### Location Features — OSM (S09/S10/S11)

18 Geofabrik GPKG layers loaded source-faithful into `bronze_location`. CRS is EPSG:4326.
All tables share a base schema; some layers have extra fields.

```sql
-- ── Base schema (12 layers) ────────────────────────────────────────────────
-- raw_osm_pois, raw_osm_pois_a, raw_osm_pofw, raw_osm_pofw_a,
-- raw_osm_transport, raw_osm_transport_a, raw_osm_traffic, raw_osm_traffic_a,
-- raw_osm_landuse_a, raw_osm_natural, raw_osm_natural_a, raw_osm_water_a

CREATE TABLE bronze_location.raw_osm_pois (       -- example: 174,233 rows
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,                     -- e.g. restaurant, pharmacy, school
    name                 TEXT,
    geom                 GEOMETRY(POINT, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);
-- Polygon variants use GEOMETRY(MULTIPOLYGON, 4326)

-- ── Roads (1.55M lines) ───────────────────────────────────────────────────
CREATE TABLE bronze_location.raw_osm_roads (
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,                     -- motorway, primary, residential, track, ...
    name                 TEXT,
    ref                  TEXT,                     -- road reference (e.g. 'A1', 'EN1')
    oneway               TEXT,                     -- 'B', 'F', 'T'
    maxspeed             INTEGER,                  -- km/h
    layer                INTEGER,                  -- vertical layer (bridges/tunnels)
    bridge               TEXT,                     -- 'T' / 'F'
    tunnel               TEXT,                     -- 'T' / 'F'
    geom                 GEOMETRY(LINESTRING, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Railways (10.6K lines) ────────────────────────────────────────────────
CREATE TABLE bronze_location.raw_osm_railways (
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,                     -- rail, subway, tram, light_rail
    name                 TEXT,
    layer                INTEGER,
    bridge               TEXT,
    tunnel               TEXT,
    geom                 GEOMETRY(LINESTRING, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Places (31.5K points + 694 polygons) ──────────────────────────────────
CREATE TABLE bronze_location.raw_osm_places (
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,                     -- city, town, village, suburb
    population           INTEGER,
    name                 TEXT,
    geom                 GEOMETRY(POINT, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Buildings (2.1M polygons) ─────────────────────────────────────────────
CREATE TABLE bronze_location.raw_osm_buildings_a (
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,
    name                 TEXT,
    type                 TEXT,                     -- building type tag
    geom                 GEOMETRY(MULTIPOLYGON, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Waterways (119K lines) ────────────────────────────────────────────────
CREATE TABLE bronze_location.raw_osm_waterways (
    osm_id               TEXT,
    code                 INTEGER,
    fclass               TEXT,
    width                INTEGER,
    name                 TEXT,
    geom                 GEOMETRY(LINESTRING, 4326),
    _load_timestamp      TIMESTAMPTZ DEFAULT NOW()
);

-- Total: 18 tables, 5,183,696 features
```

#### Location Features — Non-OSM (S22 Schools, S23 Healthcare, S24 GTFS)

These tables are for future sprints — not yet loaded.

```sql
CREATE TABLE bronze_location.raw_schools (
    id                   BIGSERIAL PRIMARY KEY,
    school_code          VARCHAR(20),
    school_name          VARCHAR(300),
    school_type          VARCHAR(50),
    education_level      VARCHAR(50),
    address_raw          TEXT,
    municipality_raw     VARCHAR(100),
    exam_year            SMALLINT,
    exam_subject         VARCHAR(100),
    exam_avg_score       NUMERIC(5,2),
    exam_pass_rate       NUMERIC(5,2),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _scrape_date         DATE
);

CREATE TABLE bronze_location.raw_healthcare (
    id                   BIGSERIAL PRIMARY KEY,
    facility_name        VARCHAR(300),
    facility_type        VARCHAR(50),
    address_raw          TEXT,
    municipality_raw     VARCHAR(100),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    has_emergency        BOOLEAN,
    _ingested_at         TIMESTAMPTZ DEFAULT NOW()
);
```

#### Regulatory & Geo (S19 PDM, S20 ARU)

```sql
CREATE TABLE bronze_regulatory.raw_pdm_zones (
    id                   BIGSERIAL PRIMARY KEY,
    municipality_code    CHAR(4),
    municipality_name    VARCHAR(100),
    zone_code            VARCHAR(30),
    zone_name            VARCHAR(200),
    zone_category        VARCHAR(50),
    max_building_height  NUMERIC(5,1),
    max_floors           SMALLINT,
    geom                 GEOMETRY(MULTIPOLYGON, 4326),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(100),
    _pdm_revision_year   SMALLINT
);
CREATE INDEX idx_pdm_geom ON bronze_regulatory.raw_pdm_zones USING GIST(geom);

CREATE TABLE bronze_geo.raw_aru_zones (
    id                   BIGSERIAL PRIMARY KEY,
    aru_name             VARCHAR(200),
    municipality_code    CHAR(4),
    designation_year     SMALLINT,
    dre_reference        TEXT,
    geom                 GEOMETRY(MULTIPOLYGON, 4326),
    _ingested_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_aru_geom ON bronze_geo.raw_aru_zones USING GIST(geom);
```

### 8.3 Silver Layer — Cleaned, Conformed, Geocoded

#### Unified Listings (anchor table for all property analysis)

```sql
CREATE TABLE silver_properties.unified_listings (
    listing_key          BIGSERIAL PRIMARY KEY,
    property_hash        VARCHAR(64) NOT NULL,         -- Dedup key: hash(address + area + typology)

    -- Source tracking
    source               VARCHAR(30) NOT NULL,         -- 'idealista', 'imovirtual'
    source_listing_id    VARCHAR(50) NOT NULL,
    listing_url          TEXT,

    -- Operation
    operation_type       VARCHAR(10) NOT NULL,         -- 'sale', 'rent'

    -- Pricing
    price_eur            NUMERIC(12,2),
    price_per_sqm        NUMERIC(10,2),

    -- Property attributes
    property_type_key    INTEGER REFERENCES gold_analytics.dim_property_type(property_type_key),
    typology             VARCHAR(10),
    useful_area_m2       NUMERIC(10,2),
    gross_area_m2        NUMERIC(10,2),
    plot_area_m2         NUMERIC(12,2),
    num_rooms            SMALLINT,
    num_bathrooms        SMALLINT,
    floor_number         SMALLINT,
    construction_year    SMALLINT,
    condition            VARCHAR(30),
    energy_class         CHAR(2),                     -- From listing data (not ADENE in MVP)

    -- Amenity flags
    has_elevator         BOOLEAN,
    has_parking          BOOLEAN,
    has_terrace          BOOLEAN,
    has_garden           BOOLEAN,
    has_pool             BOOLEAN,

    -- Geography (resolved)
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    freguesia_code       CHAR(6),
    concelho_code        CHAR(4),
    distrito_code        CHAR(2),
    address_clean        TEXT,
    postal_code          VARCHAR(10),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    geom_pt              GEOMETRY(POINT, 3763),
    geocode_confidence   NUMERIC(3,2),

    -- Listing lifecycle
    first_seen_date      DATE,
    last_seen_date       DATE,
    listing_age_days     INTEGER,
    is_active            BOOLEAN,
    price_change_count   SMALLINT DEFAULT 0,
    initial_price_eur    NUMERIC(12,2),

    _created_at          TIMESTAMPTZ DEFAULT NOW(),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_ul_geom ON silver_properties.unified_listings USING GIST(geom);
CREATE INDEX idx_ul_geom_pt ON silver_properties.unified_listings USING GIST(geom_pt);
CREATE INDEX idx_ul_geo ON silver_properties.unified_listings(geo_key);
CREATE INDEX idx_ul_active ON silver_properties.unified_listings(is_active) WHERE is_active;
CREATE INDEX idx_ul_hash ON silver_properties.unified_listings(property_hash);
CREATE INDEX idx_ul_op ON silver_properties.unified_listings(operation_type);

-- Price history tracking (SCD Type 2)
CREATE TABLE silver_properties.listing_price_history (
    id                   BIGSERIAL PRIMARY KEY,
    listing_key          BIGINT REFERENCES silver_properties.unified_listings(listing_key),
    price_eur            NUMERIC(12,2),
    price_per_sqm        NUMERIC(10,2),
    observed_date        DATE NOT NULL,
    price_change_pct     NUMERIC(6,2),
    _source              VARCHAR(30)
);
CREATE INDEX idx_ph_listing ON silver_properties.listing_price_history(listing_key, observed_date);

-- Cross-portal deduplication tracking
CREATE TABLE silver_properties.listing_matches (
    match_id             BIGSERIAL PRIMARY KEY,
    canonical_listing_key BIGINT,
    source_a             VARCHAR(30),
    source_a_id          VARCHAR(50),
    source_b             VARCHAR(30),
    source_b_id          VARCHAR(50),
    match_stage          SMALLINT,                    -- 1=exact_geo, 2=fuzzy_addr, 3=image_hash
    match_confidence     NUMERIC(3,2),
    matched_at           TIMESTAMPTZ DEFAULT NOW()
);
```

#### Census Demographics

```sql
CREATE TABLE silver_geo.census_demographics (
    geo_key              INTEGER PRIMARY KEY REFERENCES gold_analytics.dim_geography(geo_key),
    freguesia_code       CHAR(6) NOT NULL,

    total_population     INTEGER,
    pop_0_14             INTEGER,
    pop_15_24            INTEGER,
    pop_25_64            INTEGER,
    pop_65_plus          INTEGER,
    median_age           NUMERIC(4,1),
    aging_index          NUMERIC(6,2),

    total_households     INTEGER,
    avg_household_size   NUMERIC(3,1),
    single_person_hh_pct NUMERIC(5,2),

    total_foreign        INTEGER,
    foreign_pct          NUMERIC(5,2),

    pop_higher_ed_pct    NUMERIC(5,2),

    employment_rate      NUMERIC(5,2),
    unemployment_rate    NUMERIC(5,2),

    total_dwellings      INTEGER,
    occupied_dwellings   INTEGER,
    vacant_dwellings     INTEGER,
    vacancy_rate         NUMERIC(5,2),
    owner_occupied_pct   NUMERIC(5,2),
    renter_pct           NUMERIC(5,2),
    avg_dwelling_area_m2 NUMERIC(6,1),

    census_year          SMALLINT DEFAULT 2021,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

#### Zoning & ARU

```sql
CREATE TABLE silver_geo.zoning (
    zone_key             BIGSERIAL PRIMARY KEY,
    municipality_code    CHAR(4),
    zone_category        VARCHAR(30) NOT NULL,
    zone_subcategory     VARCHAR(50),
    original_zone_code   VARCHAR(30),
    original_zone_name   VARCHAR(200),
    max_building_height  NUMERIC(5,1),
    max_floors           SMALLINT,
    max_construction_idx NUMERIC(4,2),
    is_buildable         BOOLEAN,
    is_aru               BOOLEAN,
    geom                 GEOMETRY(MULTIPOLYGON, 4326),
    area_m2              NUMERIC(15,2),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_zoning_geom ON silver_geo.zoning USING GIST(geom);
```

#### Location Features

```sql
CREATE TABLE silver_location.transport_stops (
    stop_key             BIGSERIAL PRIMARY KEY,
    stop_name            VARCHAR(200),
    stop_type            VARCHAR(30) NOT NULL,
    operator             VARCHAR(100),
    is_interchange       BOOLEAN,
    route_count          INTEGER,
    service_frequency    VARCHAR(20),
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    geom_pt              GEOMETRY(POINT, 3763),
    is_planned           BOOLEAN DEFAULT FALSE,
    planned_opening_year SMALLINT,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_ts_geom ON silver_location.transport_stops USING GIST(geom);
CREATE INDEX idx_ts_geom_pt ON silver_location.transport_stops USING GIST(geom_pt);

CREATE TABLE silver_location.schools (
    school_key           BIGSERIAL PRIMARY KEY,
    school_code          VARCHAR(20),
    school_name          VARCHAR(300),
    school_type          VARCHAR(30),
    education_level      VARCHAR(30),
    avg_exam_score       NUMERIC(5,2),
    exam_pass_rate       NUMERIC(5,2),
    quality_percentile   NUMERIC(5,2),
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    geom_pt              GEOMETRY(POINT, 3763),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_schools_geom ON silver_location.schools USING GIST(geom);
CREATE INDEX idx_schools_geom_pt ON silver_location.schools USING GIST(geom_pt);

CREATE TABLE silver_location.healthcare_facilities (
    facility_key         BIGSERIAL PRIMARY KEY,
    facility_name        VARCHAR(300),
    facility_type        VARCHAR(30),
    operator_type        VARCHAR(20),
    operator_name        VARCHAR(200),
    has_emergency        BOOLEAN,
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    geom_pt              GEOMETRY(POINT, 3763),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_hf_geom ON silver_location.healthcare_facilities USING GIST(geom);
CREATE INDEX idx_hf_geom_pt ON silver_location.healthcare_facilities USING GIST(geom_pt);

CREATE TABLE silver_location.osm_pois (
    poi_key              BIGSERIAL PRIMARY KEY,
    osm_id               BIGINT NOT NULL,
    name                 VARCHAR(300),
    fclass               VARCHAR(50) NOT NULL,           -- OSM feature class (e.g. restaurant, pharmacy)
    category             VARCHAR(30),                    -- Grouped category (food, health, education, ...)
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    geom_pt              GEOMETRY(POINT, 3763),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pois_silver_geom ON silver_location.osm_pois USING GIST(geom);
CREATE INDEX idx_pois_silver_geom_pt ON silver_location.osm_pois USING GIST(geom_pt);
CREATE INDEX idx_pois_silver_fclass ON silver_location.osm_pois(fclass);
```

#### Market Context

```sql
CREATE TABLE silver_market.macro_timeseries (
    id                   BIGSERIAL PRIMARY KEY,
    indicator_code       VARCHAR(50) NOT NULL,
    indicator_name       VARCHAR(300) NOT NULL,
    category             VARCHAR(50) NOT NULL,
    source               VARCHAR(30) NOT NULL,
    observation_date     DATE NOT NULL,
    period_type          VARCHAR(10),
    value                NUMERIC(20,6),
    unit                 VARCHAR(50),
    mom_change           NUMERIC(10,4),
    qoq_change           NUMERIC(10,4),
    yoy_change           NUMERIC(10,4),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_macro_ind ON silver_market.macro_timeseries(indicator_code, observation_date);

CREATE TABLE silver_market.str_registry (
    str_key              BIGSERIAL PRIMARY KEY,
    rnal_number          VARCHAR(30),
    airbnb_listing_id    BIGINT,
    establishment_type   VARCHAR(50),
    capacity_guests      SMALLINT,
    is_licensed          BOOLEAN,
    status               VARCHAR(30),
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    avg_nightly_rate_eur NUMERIC(10,2),
    estimated_occupancy  NUMERIC(5,2),
    reviews_per_month    NUMERIC(6,2),
    estimated_monthly_rev NUMERIC(10,2),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_str_geom ON silver_market.str_registry USING GIST(geom);
```

#### Reference Tables

```sql
-- Renovation costs (manually seeded — replaces IMPIC S25 in MVP)
CREATE TABLE silver_ref.renovation_costs (
    id                   SERIAL PRIMARY KEY,
    renovation_level     VARCHAR(20) NOT NULL,
    building_age_bucket  VARCHAR(20) NOT NULL,
    municipality_tier    VARCHAR(10) NOT NULL,
    base_cost_sqm        NUMERIC(10,2),
    contingency_pct      NUMERIC(4,2) DEFAULT 0.15,
    estimated_months     SMALLINT,
    valid_from           DATE,
    source               VARCHAR(100) DEFAULT 'market_research_2024',
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Seed data (approximate 2024 values)
INSERT INTO silver_ref.renovation_costs
    (renovation_level, building_age_bucket, municipality_tier, base_cost_sqm, estimated_months)
VALUES
    ('light',  'post_2000',  'lisbon', 250,  2),
    ('light',  'post_2000',  'porto',  220,  2),
    ('light',  'post_2000',  'urban',  200,  2),
    ('light',  'post_2000',  'rural',  180,  2),
    ('medium', '1980_2000',  'lisbon', 600,  4),
    ('medium', '1980_2000',  'porto',  500,  4),
    ('medium', '1980_2000',  'urban',  450,  4),
    ('medium', '1950_1980',  'lisbon', 750,  5),
    ('medium', '1950_1980',  'porto',  650,  5),
    ('deep',   '1950_1980',  'lisbon', 1100, 8),
    ('deep',   '1950_1980',  'porto',  950,  8),
    ('deep',   'pre_1950',   'lisbon', 1500, 12),
    ('deep',   'pre_1950',   'porto',  1300, 10),
    ('deep',   'pre_1950',   'urban',  1000, 10);

-- IMT transfer tax brackets
CREATE TABLE silver_ref.imt_brackets (
    id                   SERIAL PRIMARY KEY,
    bracket_type         VARCHAR(30) NOT NULL,
    min_value            NUMERIC(12,2),
    max_value            NUMERIC(12,2),
    rate                 NUMERIC(6,4),
    deduction            NUMERIC(12,2),
    valid_year           SMALLINT,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- IMI property tax rates per municipality
CREATE TABLE silver_ref.imi_rates (
    id                   SERIAL PRIMARY KEY,
    municipality_code    CHAR(4) NOT NULL,
    municipality_name    VARCHAR(100),
    urban_rate           NUMERIC(5,4),
    rural_rate           NUMERIC(5,4),
    valid_year           SMALLINT,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Unit premiums for UC-2 pricing
CREATE TABLE silver_ref.unit_premiums (
    id                   SERIAL PRIMARY KEY,
    premium_type         VARCHAR(30) NOT NULL,
    premium_subtype      VARCHAR(30),
    market_area          VARCHAR(20),
    premium_pct          NUMERIC(6,2),
    premium_eur_sqm      NUMERIC(10,2),
    premium_lump_eur     NUMERIC(12,2),
    data_points          INTEGER,
    confidence_level     VARCHAR(10),
    notes                TEXT,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 8.4 Gold Layer — Shared Analytical Models

#### Property Location Scores

```sql
CREATE TABLE gold_analytics.property_location_scores (
    listing_key          BIGINT PRIMARY KEY,

    -- Transport accessibility (0-100)
    transport_score      NUMERIC(5,2),
    nearest_metro_m      INTEGER,
    nearest_metro_name   VARCHAR(200),
    nearest_train_m      INTEGER,
    nearest_train_name   VARCHAR(200),
    bus_stops_500m       INTEGER,
    transit_routes_500m  INTEGER,

    -- Drive-time accessibility
    drive_city_center_min NUMERIC(5,1),
    drive_airport_min    NUMERIC(5,1),
    drive_nearest_hospital_min NUMERIC(5,1),

    -- Education (0-100) — NULL until S22 ingested in Sprint 7
    education_score      NUMERIC(5,2),
    schools_1km          INTEGER,
    best_school_1km_score NUMERIC(5,2),

    -- Healthcare (0-100) — NULL until S23 ingested in Sprint 7
    healthcare_score     NUMERIC(5,2),
    nearest_hospital_m   INTEGER,
    nearest_pharmacy_m   INTEGER,

    -- Amenities / Walkability (0-100)
    walkability_score    NUMERIC(5,2),
    restaurants_500m     INTEGER,
    supermarkets_1km     INTEGER,
    total_pois_500m      INTEGER,

    -- Composite
    overall_location_score NUMERIC(5,2),

    _computed_at         TIMESTAMPTZ DEFAULT NOW()
);
```

#### Hedonic Features (MVP version — adapted for 24 sources)

```sql
CREATE TABLE gold_analytics.hedonic_features (
    listing_key            BIGINT PRIMARY KEY,

    -- Target
    price_sqm              NUMERIC(10,2),
    log_price_sqm          NUMERIC(8,4),

    -- Property intrinsics (from listings S03/S05)
    useful_area_m2         NUMERIC(10,2),
    log_area               NUMERIC(8,4),
    typology_rooms         SMALLINT,
    num_bathrooms          SMALLINT,
    floor_number           SMALLINT,
    is_ground_floor        BOOLEAN,
    is_top_floor           BOOLEAN,
    has_elevator           BOOLEAN,
    has_parking            BOOLEAN,
    has_terrace            BOOLEAN,
    has_garden             BOOLEAN,
    has_pool               BOOLEAN,
    building_age_years     SMALLINT,
    building_age_bucket    VARCHAR(20),
    energy_class_numeric   SMALLINT,          -- From listing data, not ADENE
    condition_code         SMALLINT,

    -- Location scores (from S09/S10/S11, S22/S23 when available)
    transport_score        NUMERIC(5,2),
    walkability_score      NUMERIC(5,2),
    education_score        NUMERIC(5,2),      -- NULL until S22 loaded
    healthcare_score       NUMERIC(5,2),      -- NULL until S23 loaded
    overall_location_score NUMERIC(5,2),
    nearest_metro_m        INTEGER,
    nearest_train_m        INTEGER,
    drive_city_center_min  NUMERIC(5,1),
    drive_airport_min      NUMERIC(5,1),
    restaurants_500m       INTEGER,
    supermarkets_1km       INTEGER,

    -- Neighbourhood context (from S01/S03)
    area_median_price_sqm  NUMERIC(10,2),
    area_txn_yoy_change    NUMERIC(6,2),
    area_inventory_months  NUMERIC(5,1),

    -- Demographics (from S12 Census)
    pop_density_km2        NUMERIC(10,2),
    foreign_resident_pct   NUMERIC(5,2),
    higher_education_pct   NUMERIC(5,2),
    housing_vacancy_rate   NUMERIC(5,2),
    median_age_area        NUMERIC(4,1),

    -- Regulatory (from S19, NULL outside LX/Porto)
    zone_category          VARCHAR(30),
    is_aru                 BOOLEAN,           -- From S20 when available

    -- STR context (from S15)
    al_density_pct         NUMERIC(5,2),

    -- Geography keys
    freguesia_code         CHAR(6),
    concelho_code          CHAR(4),
    operation_type         VARCHAR(10),

    _computed_at           TIMESTAMPTZ DEFAULT NOW()
);

-- NOTE: Fields EXCLUDED from MVP (deferred P3/P4 sources):
-- noise_level_db (S27), flood_risk_level (S35),
-- seismic_zone (LNEC), nearest_beach_m (compute post-MVP)
```

#### Property Comparables

```sql
CREATE TABLE gold_analytics.property_comparables (
    id                       BIGSERIAL PRIMARY KEY,
    listing_key              BIGINT NOT NULL,
    comp_listing_key         BIGINT NOT NULL,
    similarity_score         NUMERIC(5,4),
    distance_m               INTEGER,
    price_sqm_diff           NUMERIC(10,2),
    area_diff_pct            NUMERIC(6,2),
    same_typology            BOOLEAN,
    same_condition           BOOLEAN,
    same_freguesia           BOOLEAN,
    comp_rank                SMALLINT,
    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_comps_listing ON gold_analytics.property_comparables(listing_key, comp_rank);
```

#### Neighbourhood Market Stats

```sql
CREATE TABLE gold_analytics.neighbourhood_market_stats (
    id                       BIGSERIAL PRIMARY KEY,
    geo_key                  INTEGER NOT NULL,
    observation_date         DATE NOT NULL,
    operation_type           VARCHAR(10),
    active_listings          INTEGER,
    median_price_sqm         NUMERIC(10,2),
    avg_price_sqm            NUMERIC(10,2),
    p25_price_sqm            NUMERIC(10,2),
    p75_price_sqm            NUMERIC(10,2),
    median_area_m2           NUMERIC(10,2),
    avg_listing_age_days     NUMERIC(6,1),
    new_listings_7d          INTEGER,
    delisted_7d              INTEGER,
    inventory_months         NUMERIC(5,1),
    asking_vs_transaction_gap NUMERIC(6,2),
    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_nms_geo ON gold_analytics.neighbourhood_market_stats(geo_key, observation_date);
```

### 8.5 Gold Layer — UC-1: Investment Analysis

#### Property Valuation

```sql
CREATE TABLE gold_analytics.property_valuation (
    listing_key              BIGINT PRIMARY KEY,
    predicted_price_sqm      NUMERIC(10,2),
    prediction_model         VARCHAR(30),
    prediction_r2            NUMERIC(5,4),
    comp_weighted_price_sqm  NUMERIC(10,2),
    comp_count_used          SMALLINT,
    blended_fair_value_sqm   NUMERIC(10,2),
    blended_gap_pct          NUMERIC(6,2),
    valuation_signal         VARCHAR(20),
    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_val_signal ON gold_analytics.property_valuation(valuation_signal);
```

#### Investment Yield Analysis

```sql
CREATE TABLE gold_analytics.investment_yield_analysis (
    listing_key              BIGINT PRIMARY KEY,
    estimated_monthly_rent   NUMERIC(10,2),
    gross_rental_yield_pct   NUMERIC(5,2),
    net_rental_yield_pct     NUMERIC(5,2),
    str_gross_rev_monthly    NUMERIC(10,2),
    str_net_yield_pct        NUMERIC(5,2),
    str_is_licensable        BOOLEAN,
    total_acquisition_cost   NUMERIC(12,2),
    annual_holding_cost      NUMERIC(10,2),
    cash_on_cash_return_pct  NUMERIC(6,2),
    total_return_5y_pct      NUMERIC(6,2),
    yield_tier               VARCHAR(20),
    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
```

#### Renovation Opportunity (MVP — uses reference table, not IMPIC)

```sql
CREATE TABLE gold_analytics.renovation_opportunity (
    listing_key              BIGINT PRIMARY KEY,
    current_price_eur        NUMERIC(12,2),
    current_price_sqm        NUMERIC(10,2),
    current_condition        VARCHAR(30),
    current_energy_class     CHAR(2),
    useful_area_m2           NUMERIC(10,2),
    construction_year        SMALLINT,

    reno_cost_sqm_low        NUMERIC(10,2),
    reno_cost_sqm_mid        NUMERIC(10,2),
    reno_cost_sqm_high       NUMERIC(10,2),
    reno_cost_total_mid      NUMERIC(12,2),

    post_reno_price_sqm      NUMERIC(10,2),
    post_reno_price_eur      NUMERIC(12,2),

    total_investment_mid     NUMERIC(12,2),
    gross_profit_mid         NUMERIC(12,2),
    roi_pct_mid              NUMERIC(6,2),

    is_aru                   BOOLEAN,
    aru_tax_benefit_est      NUMERIC(12,2),

    estimated_reno_months    SMALLINT,
    opportunity_tier         VARCHAR(20),

    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_reno_tier ON gold_analytics.renovation_opportunity(opportunity_tier);
```

#### Neighbourhood Trajectory (MVP — uses listing trends, not permits)

```sql
CREATE TABLE gold_analytics.neighbourhood_trajectory (
    geo_key                  INTEGER PRIMARY KEY,
    freguesia_code           CHAR(6) NOT NULL,
    observation_date         DATE NOT NULL,

    price_yoy_change_pct     NUMERIC(6,2),
    price_3y_cagr_pct        NUMERIC(6,2),
    price_momentum_score     NUMERIC(5,2),

    inventory_months         NUMERIC(5,1),
    inventory_trend          VARCHAR(10),
    absorption_rate_30d      NUMERIC(5,2),
    new_listings_trend       VARCHAR(10),          -- Replaces building permits (S21 deferred)
    listing_volume_yoy_pct   NUMERIC(6,2),

    pop_change_5y_pct        NUMERIC(6,2),
    foreign_pop_change_pct   NUMERIC(6,2),
    young_professional_index NUMERIC(5,2),

    planned_metro_station    BOOLEAN,
    planned_metro_distance_m INTEGER,
    planned_metro_year       SMALLINT,
    is_aru                   BOOLEAN,

    renovation_listing_pct   NUMERIC(5,2),

    trajectory_score         NUMERIC(5,2),
    trajectory_label         VARCHAR(20),

    _computed_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_traj_score ON gold_analytics.neighbourhood_trajectory(trajectory_score DESC);
```

#### Area Catalysts (manually curated)

```sql
CREATE TABLE gold_analytics.area_catalysts (
    id                       SERIAL PRIMARY KEY,
    catalyst_type            VARCHAR(30) NOT NULL,
    catalyst_name            VARCHAR(200),
    description              TEXT,
    status                   VARCHAR(20),
    expected_completion_year SMALLINT,
    geo_key                  INTEGER,
    latitude                 NUMERIC(10,7),
    longitude                NUMERIC(10,7),
    geom                     GEOMETRY(POINT, 4326),
    impact_radius_m          INTEGER,
    estimated_price_impact   NUMERIC(5,2),
    _updated_at              TIMESTAMPTZ DEFAULT NOW()
);
```

#### Investment Opportunities (final UC-1 output — materialized view)

```sql
CREATE MATERIALIZED VIEW gold_reporting.investment_opportunities AS
SELECT
    l.listing_key,
    l.source,
    l.listing_url,
    l.price_eur,
    l.price_per_sqm,
    l.typology,
    l.useful_area_m2,
    l.condition,
    l.energy_class,
    l.construction_year,
    l.listing_age_days,
    l.latitude, l.longitude,
    g.freguesia_name, g.concelho_name, g.distrito_name,

    -- Valuation
    v.predicted_price_sqm,
    v.blended_fair_value_sqm,
    v.blended_gap_pct,
    v.valuation_signal,

    -- Yield
    y.gross_rental_yield_pct,
    y.net_rental_yield_pct,
    y.str_net_yield_pct,
    y.cash_on_cash_return_pct,
    y.total_return_5y_pct,

    -- Renovation
    r.roi_pct_mid AS renovation_roi,
    r.is_aru,
    r.opportunity_tier AS reno_tier,

    -- Trajectory
    t.trajectory_score,
    t.trajectory_label,
    t.price_yoy_change_pct AS area_price_trend,

    -- Location
    ls.overall_location_score,
    ls.transport_score,

    -- Composite investment score (transparent formula)
    GREATEST(0, LEAST(100,
        50
        - COALESCE(v.blended_gap_pct, 0) * 1.5
        + COALESCE(y.net_rental_yield_pct, 0) * 3
        + COALESCE(r.roi_pct_mid, 0) * 0.1
        + COALESCE(t.trajectory_score, 50) * 0.2
        + COALESCE(ls.overall_location_score, 50) * 0.1
        - GREATEST(l.listing_age_days - 30, 0) * 0.05
    )) AS investment_score

FROM silver_properties.unified_listings l
LEFT JOIN gold_analytics.dim_geography g ON l.geo_key = g.geo_key
LEFT JOIN gold_analytics.property_valuation v ON l.listing_key = v.listing_key
LEFT JOIN gold_analytics.investment_yield_analysis y ON l.listing_key = y.listing_key
LEFT JOIN gold_analytics.renovation_opportunity r ON l.listing_key = r.listing_key
LEFT JOIN gold_analytics.neighbourhood_trajectory t ON l.geo_key = t.geo_key
LEFT JOIN gold_analytics.property_location_scores ls ON l.listing_key = ls.listing_key
WHERE l.is_active AND l.operation_type = 'sale';

CREATE INDEX idx_inv_score ON gold_reporting.investment_opportunities(investment_score DESC);
```

### 8.6 Gold Layer — UC-2: Pricing Strategy

#### Development Projects & Units

```sql
CREATE TABLE gold_analytics.development_projects (
    project_key          SERIAL PRIMARY KEY,
    project_name         VARCHAR(200),
    developer_name       VARCHAR(200),
    geo_key              INTEGER,
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    total_units          INTEGER,
    total_area_m2        NUMERIC(12,2),
    land_cost_eur        NUMERIC(14,2),
    construction_cost_eur NUMERIC(14,2),
    other_costs_eur      NUMERIC(14,2),
    total_cost_eur       NUMERIC(14,2),
    target_margin_pct    NUMERIC(5,2),
    expected_completion  DATE,
    status               VARCHAR(30),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE gold_analytics.development_units (
    unit_key             SERIAL PRIMARY KEY,
    project_key          INTEGER REFERENCES gold_analytics.development_projects(project_key),
    unit_identifier      VARCHAR(20),
    typology             VARCHAR(10),
    useful_area_m2       NUMERIC(10,2),
    terrace_area_m2      NUMERIC(10,2),
    floor_number         SMALLINT,
    orientation          VARCHAR(20),
    view_type            VARCHAR(30),
    has_parking          BOOLEAN,
    parking_spaces       SMALLINT,
    has_storage          BOOLEAN,
    storage_area_m2      NUMERIC(6,1),
    unit_construction_cost NUMERIC(12,2),
    status               VARCHAR(20),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

#### Competitive Developments

```sql
CREATE TABLE gold_analytics.competitive_developments (
    id                   SERIAL PRIMARY KEY,
    project_name         VARCHAR(200),
    developer_name       VARCHAR(200),
    geo_key              INTEGER,
    latitude             NUMERIC(10,7),
    longitude            NUMERIC(10,7),
    geom                 GEOMETRY(POINT, 4326),
    distance_to_project_m INTEGER,
    total_units          INTEGER,
    units_sold           INTEGER,
    units_available      INTEGER,
    avg_price_sqm        NUMERIC(10,2),
    min_price_sqm        NUMERIC(10,2),
    max_price_sqm        NUMERIC(10,2),
    absorption_rate_monthly NUMERIC(5,2),
    launch_date          DATE,
    expected_completion  DATE,
    quality_tier         VARCHAR(20),
    _scrape_date         DATE,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

#### Absorption Rate Model & Location Premiums

```sql
CREATE TABLE gold_analytics.absorption_rate_model (
    id                   SERIAL PRIMARY KEY,
    geo_key              INTEGER,
    typology             VARCHAR(10),
    price_segment        VARCHAR(20),
    observation_period   VARCHAR(10),
    avg_days_on_market   NUMERIC(6,1),
    median_days_on_market NUMERIC(6,1),
    pct_sold_30d         NUMERIC(5,2),
    pct_sold_60d         NUMERIC(5,2),
    pct_sold_90d         NUMERIC(5,2),
    sample_size          INTEGER,
    _computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE gold_analytics.location_price_premiums (
    id                   SERIAL PRIMARY KEY,
    feature_name         VARCHAR(50) NOT NULL,
    feature_value        VARCHAR(50),
    coefficient_eur_sqm  NUMERIC(10,2),
    coefficient_pct      NUMERIC(6,2),
    std_error            NUMERIC(10,4),
    t_statistic          NUMERIC(8,4),
    p_value              NUMERIC(8,6),
    scope                VARCHAR(20),
    model_version        VARCHAR(20),
    calibration_date     DATE,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

#### Unit Pricing Recommendation (MVP — no noise discount)

```sql
CREATE TABLE gold_analytics.unit_pricing_recommendation (
    unit_key                    INTEGER PRIMARY KEY,
    project_key                 INTEGER NOT NULL,

    comp_median_price_sqm       NUMERIC(10,2),
    comp_weighted_price_sqm     NUMERIC(10,2),
    comp_count                  INTEGER,

    hedonic_base_price_sqm      NUMERIC(10,2),

    floor_premium_sqm           NUMERIC(10,2),
    view_premium_sqm            NUMERIC(10,2),
    orientation_premium_sqm     NUMERIC(10,2),
    terrace_premium_sqm         NUMERIC(10,2),
    garden_premium_sqm          NUMERIC(10,2),
    parking_premium_total       NUMERIC(10,2),
    storage_premium_total       NUMERIC(10,2),
    energy_premium_sqm          NUMERIC(10,2),
    size_adjustment_sqm         NUMERIC(10,2),
    newness_premium_sqm         NUMERIC(10,2),
    development_quality_sqm     NUMERIC(10,2),
    -- noise_discount_sqm REMOVED (needs S27, deferred to post-MVP)
    total_adjustments_sqm       NUMERIC(10,2),

    recommended_price_sqm       NUMERIC(10,2),
    recommended_price_eur       NUMERIC(12,2),
    price_range_low_eur         NUMERIC(12,2),
    price_range_high_eur        NUMERIC(12,2),

    vs_area_new_median_pct      NUMERIC(6,2),
    vs_competition_avg_pct      NUMERIC(6,2),
    price_segment               VARCHAR(20),

    estimated_days_to_sell_low  INTEGER,
    estimated_days_to_sell_rec  INTEGER,
    estimated_days_to_sell_high INTEGER,

    unit_total_cost             NUMERIC(12,2),
    unit_gross_margin_eur       NUMERIC(12,2),
    unit_gross_margin_pct       NUMERIC(5,2),
    breakeven_price_eur         NUMERIC(12,2),

    pricing_confidence          VARCHAR(10),
    primary_method              VARCHAR(30),

    _computed_at                TIMESTAMPTZ DEFAULT NOW()
);
```

#### IMT Tax Calculator (embedded in DB)

```sql
CREATE FUNCTION gold_analytics.calc_imt(
    price_eur NUMERIC,
    is_primary_residence BOOLEAN DEFAULT FALSE,
    is_company BOOLEAN DEFAULT FALSE
) RETURNS NUMERIC AS $$
DECLARE
    imt_amount NUMERIC := 0;
    bracket RECORD;
    bracket_type_val VARCHAR(30);
BEGIN
    IF is_company THEN
        bracket_type_val := 'company';
    ELSIF is_primary_residence THEN
        bracket_type_val := 'primary_residence';
    ELSE
        bracket_type_val := 'secondary_residence';
    END IF;

    SELECT rate, deduction INTO bracket
    FROM silver_ref.imt_brackets
    WHERE bracket_type = bracket_type_val
      AND price_eur >= min_value
      AND (price_eur < max_value OR max_value IS NULL)
      AND valid_year = EXTRACT(YEAR FROM CURRENT_DATE)
    LIMIT 1;

    IF FOUND THEN
        imt_amount := price_eur * bracket.rate - COALESCE(bracket.deduction, 0);
    END IF;

    RETURN GREATEST(imt_amount, 0);
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 8.7 Gold Reporting — Fact Tables & Materialized Views

#### Fact: Market Transactions

```sql
CREATE TABLE gold_analytics.fact_transactions (
    transaction_key      BIGSERIAL PRIMARY KEY,
    date_key             INTEGER REFERENCES gold_analytics.dim_time(date_key),
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    property_type_key    INTEGER REFERENCES gold_analytics.dim_property_type(property_type_key),
    median_price_sqm     NUMERIC(10,2),
    transaction_count    INTEGER,
    total_value          NUMERIC(15,2),
    yoy_price_change_pct NUMERIC(6,2),
    qoq_price_change_pct NUMERIC(6,2),
    time_period          VARCHAR(10),
    geo_level            VARCHAR(20),
    _computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE gold_analytics.fact_listings_snapshot (
    snapshot_key         BIGSERIAL PRIMARY KEY,
    snapshot_date        DATE NOT NULL,
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    property_type_key    INTEGER,
    operation_type       VARCHAR(10),
    active_listing_count INTEGER,
    median_price_eur     NUMERIC(12,2),
    median_price_sqm     NUMERIC(10,2),
    avg_listing_age_days NUMERIC(6,1),
    new_listings_7d      INTEGER,
    delisted_7d          INTEGER,
    _computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE gold_analytics.fact_str_market (
    id                   BIGSERIAL PRIMARY KEY,
    snapshot_date        DATE NOT NULL,
    geo_key              INTEGER REFERENCES gold_analytics.dim_geography(geo_key),
    total_licensed_al    INTEGER,
    total_airbnb_listings INTEGER,
    al_pct_of_housing    NUMERIC(5,2),
    median_nightly_rate  NUMERIC(10,2),
    avg_occupancy_rate   NUMERIC(5,2),
    estimated_revpar     NUMERIC(10,2),
    _computed_at         TIMESTAMPTZ DEFAULT NOW()
);
```

#### Project Pricing Summary (UC-2 output — materialized view)

```sql
CREATE MATERIALIZED VIEW gold_reporting.project_pricing_summary AS
SELECT
    p.project_key,
    p.project_name,
    p.developer_name,
    p.total_units,
    p.total_cost_eur,
    p.target_margin_pct,

    COUNT(u.unit_key) AS priced_units,
    SUM(r.recommended_price_eur) AS total_revenue_at_rec,
    SUM(r.recommended_price_eur) - p.total_cost_eur AS total_profit_at_rec,
    (SUM(r.recommended_price_eur) - p.total_cost_eur) / NULLIF(p.total_cost_eur, 0) * 100
        AS blended_margin_pct,
    AVG(r.recommended_price_sqm) AS avg_price_sqm,
    AVG(r.estimated_days_to_sell_rec) AS avg_days_to_sell,
    AVG(r.vs_competition_avg_pct) AS avg_vs_competition_pct

FROM gold_analytics.development_projects p
LEFT JOIN gold_analytics.development_units u ON p.project_key = u.project_key
LEFT JOIN gold_analytics.unit_pricing_recommendation r ON u.unit_key = r.unit_key
GROUP BY p.project_key, p.project_name, p.developer_name,
         p.total_units, p.total_cost_eur, p.target_margin_pct;
```

---

# Part IV — Spatial Strategy, Pipelines & Scheduling

---

## 9. Spatial Data Strategy

### 9.1 Coordinate Reference Systems

| CRS | EPSG | Usage |
|---|---|---|
| WGS84 | 4326 | Storage default, display, web maps |
| PT-TM06/ETRS89 | 3763 | Distance calculations in meters, area computations |

All geometry columns store both:
```sql
geom    GEOMETRY(POINT, 4326)    -- For display and joins
geom_pt GEOMETRY(POINT, 3763)    -- For ST_DWithin distance queries in meters
```

### 9.2 Spatial Indexing

```sql
-- Standard GIST indexes on all geometry columns
CREATE INDEX idx_[table]_geom USING GIST (geom);

-- H3 hex index for fast aggregation (resolution 9 ≈ 0.1 km²)
ALTER TABLE silver_properties.unified_listings
    ADD COLUMN h3_index_9 VARCHAR(15);
CREATE INDEX idx_listings_h3 ON silver_properties.unified_listings (h3_index_9);
```

### 9.3 Common Spatial Query Patterns

```sql
-- Find all listings within 500m of a metro station
SELECT l.*
FROM silver_properties.unified_listings l
JOIN silver_location.transport_stops t
    ON ST_DWithin(l.geom_pt, t.geom_pt, 500)
WHERE t.stop_type = 'metro' AND l.is_active = TRUE;

-- Count POIs within walking distance
SELECT l.listing_key,
       COUNT(*) FILTER (WHERE p.category = 'food') AS food_500m,
       COUNT(*) FILTER (WHERE p.category = 'shopping') AS shopping_500m
FROM silver_properties.unified_listings l
JOIN bronze_location.raw_osm_pois p
    ON ST_DWithin(l.geom_pt, ST_Transform(p.geom, 3763), 500)
WHERE l.is_active = TRUE
GROUP BY l.listing_key;

-- Property zoning lookup
SELECT l.*, z.zone_category, z.max_floors
FROM silver_properties.unified_listings l
JOIN silver_geo.zoning z ON ST_Within(l.geom, z.geom)
WHERE l.listing_key = 12345;
```

### 9.4 Location Score Computation Logic

```
Transport score (0-100):
  40 pts: Metro/train proximity (40 if <500m, 30 if 500-1000m, 20 if 1-2km, 0 if >2km)
  30 pts: Bus coverage (scaled by stops within 500m)
  20 pts: Route diversity (scaled by unique routes within 500m)
  10 pts: Interchange bonus (within 500m of interchange)

Walkability score (0-100):
  Category-weighted POI density within 500m:
    Supermarkets (wt 20), Restaurants/Cafés (15), Pharmacies (15),
    Parks (15), Banks (10), Gyms (10), Other retail (10), Entertainment (5)

Overall location score:
  transport * 0.25 + walkability * 0.25 + education * 0.20 +
  healthcare * 0.15 + shopping_access * 0.15
```

---

## 10. Dependency Graph & Critical Path

### 10.1 Layer Dependencies

```
LAYER 0 — Geography Foundation (Sprint 1)
  S08 CAOP ──► dim_geography
  S12 Census ──► dim_geography + census_demographics
  S09/S10/S11 OSM ──► POIs, transport stops, OSRM routing
  Nominatim geocoder

LAYER 1 — Core Market Data (Sprint 2)
  S01 INE Transactions ──► fact_transactions
  S03 Idealista Sales ──► bronze_listings
  S04 Idealista Rentals ──► bronze_listings
  S17 ECB Euribor ──► macro_timeseries
  S16 BPStat ──► macro_timeseries
  S18 Eurostat HPI ──► macro_timeseries

LAYER 2 — Silver Unification (Sprint 3)
  S03+S04 listings ──► geocode → resolve to freguesia → unified_listings
  S05 Imovirtual ──► additional listings → dedup → unified_listings

LAYER 3 — Spatial Scoring (Sprint 4)
  unified_listings × POIs ──► walkability_score
  unified_listings × Transport ──► transport_score
  unified_listings × OSRM ──► drive-times
  ──► property_location_scores + neighbourhood_market_stats

LAYER 4 — Analytical Models (Sprint 5-6)
  hedonic_features → hedonic model → property_valuation
  property_comparables
  investment_yield_analysis
  renovation_opportunity
  neighbourhood_trajectory
  ──► investment_opportunities (UC-1 MVP)

LAYER 5 — Enhancements (Sprint 7)
  S06 Imovirtual Rentals, S14 RNAL, S22 Schools, S23 Healthcare, S24 GTFS
  ──► hedonic model v2 (recalibrated)

LAYER 6 — UC-2 Pricing (Sprint 8)
  S34 Competitive Developments
  absorption_rate_model + location_price_premiums
  ──► unit_pricing_recommendation (UC-2 MVP)
```

### 10.2 Critical Path

```
S08 + S12 ──► dim_geography ──► S03 geocoding ──► unified_listings
  ──► neighbourhood_market_stats ──► hedonic_features
    ──► hedonic model ──► property_valuation
      ──► investment_opportunities (UC-1 MVP at Week 12)
        ──► UC-2 additions (Week 16)

Critical path to UC-1: 6 sprints (12 weeks)
Critical path to UC-2: 8 sprints (16 weeks)
```

---

## 11. Orchestration & Scheduling

### 11.1 Airflow DAG Structure

```
dags/
├── ingestion/
│   ├── dag_caop_boundaries.py          # Sprint 1 — Annual
│   ├── dag_ine_census.py               # Sprint 1 — One-time + annual
│   ├── dag_osm_import.py               # Sprint 1 — Monthly
│   ├── dag_idealista_listings.py        # Sprint 2 — Daily
│   ├── dag_ine_transactions.py          # Sprint 2 — Quarterly
│   ├── dag_ecb_euribor.py              # Sprint 2 — Monthly
│   ├── dag_bpstat_macro.py             # Sprint 2 — Monthly
│   ├── dag_eurostat_hpi.py             # Sprint 2 — Quarterly
│   ├── dag_imovirtual_listings.py       # Sprint 3 — Daily
│   ├── dag_insideairbnb.py             # Sprint 4 — Quarterly
│   ├── dag_pdm_zoning.py               # Sprint 4 — Ad-hoc
│   ├── dag_imt_imi_rates.py            # Sprint 6 — Annual
│   ├── dag_aru_boundaries.py            # Sprint 6 — Ad-hoc
│   ├── dag_ine_rental_index.py          # Sprint 6 — Quarterly
│   ├── dag_imovirtual_rentals.py        # Sprint 7 — Weekly
│   ├── dag_rnal_scraper.py              # Sprint 7 — Monthly
│   ├── dag_infoescolas.py               # Sprint 7 — Annual
│   ├── dag_sns_facilities.py            # Sprint 7 — Quarterly
│   ├── dag_gtfs_import.py               # Sprint 7 — Quarterly
│   └── dag_competitive_devs.py          # Sprint 8 — Monthly
├── transformation/
│   ├── dag_dbt_silver.py                # Daily — all Silver models
│   ├── dag_dbt_gold.py                  # Daily — all Gold models
│   ├── dag_deduplication.py             # Daily — listing dedup
│   ├── dag_geocoding.py                 # Daily — geocode new records
│   └── dag_location_scores.py           # Weekly — recompute scores
├── quality/
│   ├── dag_data_quality.py              # Daily — dbt tests + GE checks
│   └── dag_freshness_monitor.py         # Hourly — check source freshness
└── maintenance/
    ├── dag_matview_refresh.py           # Daily — refresh materialized views
    ├── dag_vacuum_analyze.py            # Weekly — PostgreSQL maintenance
    └── dag_backup.py                    # Daily — pg_dump + MinIO backup
```

### 11.2 Schedule Map

| DAG | Schedule | Sprint | Dependencies |
|---|---|---|---|
| Idealista scraper | `0 6 * * *` (daily 6AM) | 2+ | None |
| Imovirtual scraper | `0 7 * * *` | 3+ | None |
| Geocoding pipeline | `0 9 * * *` | 2+ | After scrapers |
| Listing dedup | `0 10 * * *` | 3+ | After geocoding |
| dbt Silver run | `0 11 * * *` | 2+ | After dedup |
| dbt Gold run | `0 12 * * *` | 2+ | After Silver |
| MatView refresh | `0 13 * * *` | 6+ | After Gold |
| ECB Euribor | `0 6 1 * *` (monthly) | 2+ | None |
| INE transactions | `0 6 1 1,4,7,10 *` (quarterly) | 2+ | None |
| OSM full import | `0 2 1 * *` (monthly) | 1+ | None |
| Location scores | `0 3 * * 0` (weekly Sunday) | 4+ | After OSM |
| Data quality | `0 14 * * *` | 6+ | After Gold |
| BPStat macro | `0 6 15 * *` (monthly) | 2+ | None |
| RNAL scraper | `0 4 1 * *` (monthly) | 7+ | None |
| InfoEscolas | `0 6 15 7 *` (annual July) | 7+ | None |

---

# Part V — Delivery Plan & Operations

---

## 12. Sprint Plan (8 Sprints / 16 Weeks)

### Sprint 1 — Infrastructure & Geography (Weeks 1-2)

| Task | Source | Days | Deliverable | Status |
|---|---|---|---|---|
| Docker Compose (Airflow + MinIO) | — | 2 | Airflow UI + MinIO console running | ✅ Done |
| Airflow setup + GIS ingestion template | — | 1.5 | Reusable DAG factory for Flow C | ✅ Done |
| Airflow setup + API ingestion template | — | 1.5 | Reusable DAG factory for Flow A | ✅ Done |
| Ingest CAOP boundaries to MinIO | S08 | 0.5 | `raw/caop/2025/Continente_CAOP2025.gpkg` (180 MB) | ✅ Done |
| Ingest BGRI census to MinIO | S12 | 0.5 | `raw/bgri/2021/BGRI21_CONT.gpkg` (459 MB) | ✅ Done |
| Ingest OSM Portugal to MinIO | S09/S10/S11 | 0.5 | `raw/osm/2026-03/portugal.gpkg` (1.5 GB) | ✅ Done |
| Ingest INE API indicators | S01/S29 | 0.5 | 33 indicators × JSON in `raw/ine/` | ✅ Done |
| PostGIS warehouse service | — | 0.5 | `postgis/postgis:16-3.4` + 15 schemas | ✅ Done |
| Load CAOP → `bronze_geo.raw_caop_*` | S08 | 1 | 3,049 freguesias + 278 municipios + 18 distritos | ✅ Done |
| Load BGRI → `bronze_ine.raw_bgri` | S12 | 1 | 203,264 subsection polygons + 32 census columns | ✅ Done |
| Load OSM → `bronze_location.raw_osm_*` | S09/S10/S11 | 1 | 18 tables, 5.2M features (POIs + transport + roads + context) | ✅ Done |
| Load INE → `bronze_ine.raw_indicators` | S01/S29 | 1 | 33 indicators, 907,533 rows flattened from JSON | ✅ Done |
| Setup dbt (dbt-postgres 1.9) | — | 0.5 | dbt project, staging views, custom schema macro, Airflow DAG | ✅ Done |
| Build `gold_analytics.dim_geography` | S08 | 0.5 | 3,049 freguesias with dual-CRS geometry + census demographics (via dbt) | ✅ Done |
| Build OSRM | S11 | 2 | Routing engine serving Portugal (car :5050, walking :5051, cycling :5052) | ✅ Done |
| Setup Nominatim | (S11 PBF) | 1 | Geocoder operational on :8088 (forward + reverse) | ✅ Done |
| Start CI license enquiry | S02 | — | Email sent | Pending |

**Exit criteria:** All bronze tables populated; dim_geography live; Nominatim + OSRM responding.

### Sprint 2 — Core Market Data (Weeks 3-4)

| Task | Source | Days | Deliverable | Status |
|---|---|---|---|---|
| Idealista API integration | S03/S04 | 5 | Daily sale + rental ingestion → `bronze_listings.raw_idealista` | ✅ Done |
| Idealista bronze schema (source-oriented) | S03/S04 | 1 | Raw JSONL → PostGIS with JSONB/TEXT columns (no parsing at bronze) | ✅ Done |
| Idealista ingestion DAG refactor | S03/S04 | 1 | Config dataclass, tenacity retry, cleanup task, template alignment | ✅ Done |
| ECB Euribor | S17 | 1 | Monthly rate DAG → `bronze_macro.raw_ecb` (3 Euribor series via SDMX API) | ✅ Done |
| Banco de Portugal | S16 | 2 | Monthly macro data → `bronze_macro.raw_bpstat` (3 domains, 16 datasets via JSON-stat API) | ✅ Done |
| Eurostat HPI | S18 | 1 | Quarterly HPI → `bronze_macro.raw_eurostat` | |
| Geocoding pipeline | — | 2 | Batch geocoding operational | |
| dbt project scaffolding | — | 2 | Staging models, `dim_time`, `dim_property_type` | |

**Exit criteria:** Idealista flowing daily; macro indicators loaded; geocoding working.

### Sprint 3 — Silver Layer: Unification (Weeks 5-6)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| Listing normalization | S03/S04 | 2 | Common schema |
| Address cleaning | — | 2 | Standardized Portuguese addresses |
| Imovirtual scraper | S05 | 7 | Second portal live |
| Dedup pipeline | — | 3 | Cross-portal dedup |
| Price history tracking | — | 2 | SCD2 for price changes |
| unified_listings dbt model | — | 2 | Clean, geocoded, deduped |
| IMI/IMT reference tables | S31 | 2 | Tax brackets loaded |

**Exit criteria:** unified_listings with ~100K+ deduped active listings; >95% geocoded.

### Sprint 4 — Location Scores & Market Stats (Weeks 7-8)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| neighbourhood_market_stats | S01/S03 | 3 | Per-freguesia stats |
| Transport proximity | S10 | 2 | Nearest metro/train |
| POI density / walkability | S09 | 2 | Amenity counts |
| Drive-time via OSRM | S11 | 3 | City center, airport |
| property_location_scores | — | 2 | Composite scores |
| Inside Airbnb | S15 | 1 | STR data for LX + Porto |
| PDM Zoning (LX + Porto) | S19 | 3 | Zoning polygons |

**Exit criteria:** Every listing has location scores; neighbourhood stats computed.

### Sprint 5 — Hedonic Model & Valuation (Weeks 9-10)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| hedonic_features assembly | — | 3 | Feature vector per listing |
| Hedonic model training | — | 5 | OLS/Ridge on log(price_sqm) |
| Model validation | — | 2 | R² ≥ 0.73; MAPE < 18% |
| property_comparables | — | 3 | Top-10 comps per listing |
| property_valuation | — | 2 | Predicted price + blended gap |
| Seed renovation cost table | — | 1 | Manual cost estimates |
| Seed area catalysts | — | 2 | Known infrastructure projects |

**Exit criteria:** Every sale listing has predicted fair value and valuation_signal.

### Sprint 6 — UC-1 MVP: Investment Opportunities (Weeks 11-12)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| investment_yield_analysis | S04/S15/S31 | 4 | LTR + STR yield |
| renovation_opportunity | (ref table) | 3 | Reno cost + ROI |
| neighbourhood_trajectory | — | 3 | Trajectory scores |
| investment_opportunities view | — | 2 | **Composite score — UC-1 LIVE** |
| Metabase: Investment Dashboard | — | 3 | Map + table + filters |
| INE Rental Price Index | S29 | 0.5 | Official rents |
| ARU boundaries | S20 | 2 | ARU zones loaded |

**🏁 MILESTONE 1 (Week 12): UC-1 MVP LIVE.** Investors can query ranked opportunities.

### Sprint 7 — Enhancements + UC-2 Foundation (Weeks 13-14)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| Imovirtual rentals | S06 | 1 | Rental comps expanded |
| RNAL scraping | S14 | 5 | AL license registry |
| STR registry (RNAL + Airbnb) | S14/S15 | 2 | str_registry with licensing |
| School data (InfoEscolas) | S22 | 5 | Schools geocoded + scored |
| Healthcare facilities | S23 | 2 | Hospitals/clinics geocoded |
| GTFS transport schedules | S24 | 3 | Service frequency enrichment |
| Recalibrate hedonic model v2 | — | 2 | Add education + healthcare |
| Refresh investment_opportunities | — | 1 | Improved scores |

**Exit criteria:** Location scores include education + healthcare; STR intelligence live.

### Sprint 8 — UC-2 MVP + Production Hardening (Weeks 15-16)

| Task | Source | Days | Deliverable |
|---|---|---|---|
| Competitive developments | S34 | 5 | Competing new-builds mapped |
| absorption_rate_model | — | 3 | Days-on-market by segment |
| location_price_premiums | — | 2 | Hedonic coefficients as table |
| ref_unit_premiums calibration | — | 2 | Floor/view/orientation lookup |
| development_projects import | — | 2 | Developer project data entry |
| unit_pricing_recommendation | — | 3 | **Unit-level pricing — UC-2 LIVE** |
| project_pricing_summary | — | 1 | Aggregated project dashboard |
| Metabase: Pricing Dashboard | — | 3 | Unit matrix + competition map |
| CI data integration (if license) | S02 | 3 | Transaction pricing (if available) |
| Data quality monitoring | — | 2 | dbt tests + freshness alerts |
| Documentation | — | 2 | Data dictionary + user guide |
| Backup + recovery test | — | 1 | pg_dump restore verified |

**🏁 MILESTONE 2 (Week 16): UC-2 MVP LIVE + Production Release.**

---

## 13. Data Quality Framework

### 13.1 dbt Tests

```yaml
# models/silver/silver_properties/schema.yml
models:
  - name: unified_listings
    columns:
      - name: listing_key
        tests: [unique, not_null]
      - name: price_eur
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 1000
              max_value: 50000000
      - name: useful_area_m2
        tests:
          - dbt_utils.accepted_range:
              min_value: 5
              max_value: 10000
      - name: latitude
        tests:
          - dbt_utils.accepted_range:
              min_value: 36.9
              max_value: 42.2
      - name: longitude
        tests:
          - dbt_utils.accepted_range:
              min_value: -9.6
              max_value: -6.1
      - name: energy_class
        tests:
          - accepted_values:
              values: ['A+', 'A', 'B', 'B-', 'C', 'D', 'E', 'F']
      - name: geo_key
        tests:
          - relationships:
              to: ref('dim_geography')
              field: geo_key
```

### 13.2 Great Expectations Checks

| Check | Table | Rule | Severity |
|---|---|---|---|
| Freshness | `bronze_listings.raw_idealista` | Max 2 days since last ingest | Critical |
| Volume | `bronze_listings.raw_idealista` | Daily ingest > 1000 records | Warning |
| Null rate | `unified_listings.geo_key` | < 5% null | Critical |
| Distribution | `unified_listings.price_per_sqm` | Median €500-€20,000 | Warning |
| Referential | All Silver tables | All geo_key references valid | Critical |
| Spatial | All geocoded tables | All points within Portugal bbox | Critical |

### 13.3 Pipeline Metadata

```sql
CREATE TABLE metadata.pipeline_runs (
    run_id               BIGSERIAL PRIMARY KEY,
    dag_id               VARCHAR(100),
    task_id              VARCHAR(100),
    source               VARCHAR(50),
    target_table         VARCHAR(100),
    run_start            TIMESTAMPTZ,
    run_end              TIMESTAMPTZ,
    status               VARCHAR(20),
    records_ingested     INTEGER,
    records_rejected     INTEGER,
    error_message        TEXT,
    batch_id             VARCHAR(50)
);
```

---

## 14. Risk Register & Mitigation

| # | Risk | Prob. | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Idealista API rate limits too restrictive | Med | High | Apply for higher tier; cache unchanged listings; supplement with S05 |
| R2 | Imovirtual blocks scrapers | High | Med | Rotating proxies + user agents; reduce frequency; explore partnership |
| R3 | Hedonic R² < 0.70 without noise/flood features | Med | High | Add interaction terms; try Random Forest; segment by concelho; increase comp weight |
| R4 | CI license too expensive | Med | Low | INE + listing data sufficient for MVP; CI is enrichment |
| R5 | Nominatim geocoding quality issues | Low | High | Fallback: Google Maps API; build Portuguese address normalization |
| R6 | Server failure / data loss | Med | High | Daily pg_dump + MinIO backup to Hetzner Storage Box |
| R7 | InfoEscolas JS-heavy, breaks scraper | Med | Low | Education score stays NULL; model handles gracefully |
| R8 | RNAL scraping blocked | Med | Med | Use Inside Airbnb as STR proxy; submit FOI request |

---

## 15. Resource Requirements & Costs

### 15.1 Team

| Role | Count | Sprints | Focus |
|---|---|---|---|
| Data Engineer (Lead) | 1 | 1-8 | PG/PostGIS, dbt, Airflow, Docker |
| Data Engineer (Scraping) | 1 | 2-8 | Scrapy, Selenium, geocoding, dedup |
| Data Scientist | 0.5 | 5-8 | Hedonic model, premium calibration |

### 15.2 Budget

| Item | Monthly | Total (16 weeks) |
|---|---|---|
| Hetzner AX102 server | €85 | €340 |
| Hetzner Storage Box (backup) | €12 | €48 |
| Proxy service (scraping) | €75 | €300 |
| **Total infrastructure** | **€172** | **€688** |

Optional: CI license (€2-10K/year), Google Maps API (~€50-100/month if Nominatim insufficient).

### 15.3 Effort Summary

| Sprint | Weeks | Eng-Days | Theme | Milestone |
|---|---|---|---|---|
| 1 | 1-2 | 14 | Infrastructure + geography | Platform live |
| 2 | 3-4 | 15 | Core market data | Data flowing |
| 3 | 5-6 | 20 | Silver unification + dedup | Unified listings |
| 4 | 7-8 | 16 | Location scores | Properties enriched |
| 5 | 9-10 | 18 | Hedonic model + valuation | Valuations live |
| 6 | 11-12 | 18 | UC-1 output | 🏁 **UC-1 MVP** |
| 7 | 13-14 | 21 | Enhancements + UC-2 prep | Model v2 |
| 8 | 15-16 | 26 | UC-2 output + production | 🏁 **UC-2 MVP** |
| **Total** | **16** | **148** | | **Both use cases live** |

### 15.4 Data Volume Estimates (MVP)

| Dataset | Est. Records | Est. Storage | Growth |
|---|---|---|---|
| Listings (2 portals, historical) | ~1.5M snapshots/year | 8 GB/year | ~4K/day |
| INE transactions | ~500K records | 200 MB | Quarterly |
| Census 2021 BGRI | ~200K subsection polygons | 200-400 MB | Static (~2031) |
| CAOP boundaries | ~3,100 freguesias | 500 MB (geometries) | Annual |
| OSM Portugal | ~20M features | 5 GB | Monthly |
| RNAL | ~120K licenses | 100 MB | Monthly |
| Inside Airbnb | ~50K listings/snapshot | 200 MB/year | Quarterly |
| Macro time series | ~100K observations | 50 MB | Monthly |
| PDM zoning (LX + Porto) | ~10K zones | 2 GB (geometries) | Static |
| Transport stops | ~30K stops | 50 MB | Quarterly |
| Schools + Healthcare | ~13K facilities | 70 MB | Annual |
| Location scores | matches listing count | 500 MB | Weekly |

**Total estimated: ~20 GB in PostgreSQL + ~30 GB in MinIO**

---

## 16. Future Expansion (P3/P4 Roadmap)

Once MVP is stable (Week 16+), layer in deferred sources:

### Phase 2A — Risk & Environment (Weeks 17-20)

| Source | Value Add | Expected Improvement |
|---|---|---|
| S35 APA Flood Risk | flood_risk_level in hedonic model | +1-2% R² in flood zones |
| S27 Noise Maps (LX/Porto) | noise_level_db in hedonic + pricing | +2-3% R²; noise_discount in UC-2 |
| S13 ADENE Certificates (if FOI) | kWh/m², CO2, detailed energy | Better energy premium |

### Phase 2B — Supply Pipeline & Costs (Weeks 21-24)

| Source | Value Add |
|---|---|
| S25 IMPIC Construction Costs | Calibrate renovation cost model with real indices |
| S21 INE Building Permits | Add building permits to trajectory model |
| S28 PVGIS Solar | Precise sun exposure for orientation premiums |

### Phase 2C — Coverage & Niche (Weeks 25+)

| Source | Value Add |
|---|---|
| S07 Casa Sapo | Third listing portal; +5-10% unique listings |
| S26 DGPC Heritage | Heritage flag for renovation constraints |
| S33 Google Trends | Demand leading indicator in trajectory model |
| S30 Porta 65 Rent Caps | Government rental benchmark cross-check |
| S32 PORDATA | Additional socioeconomic granularity |
| S36 ICNF Fire Risk | Rural property risk factor |
| S37 Municipal Open Data | Hyperlocal amenity enrichment |

All deferred fields are nullable — models automatically incorporate new features without schema changes.

---

## Go/No-Go Milestones

### Milestone 1: UC-1 MVP (Week 12)

| Criteria | Target | Hard Fail? |
|---|---|---|
| dim_geography populated | ≥ 3,000 freguesias | Yes |
| unified_listings active sale count | ≥ 80,000 | Yes |
| Geocoding success rate | ≥ 95% to freguesia | Yes |
| Hedonic model R² (holdout) | ≥ 0.70 | Yes |
| property_valuation coverage | ≥ 90% of active listings | Yes |
| investment_yield available | ≥ 80% of listings with rental comps | No |
| neighbourhood_trajectory | ≥ 80% of active freguesias | No |
| Metabase Investment Dashboard | Accessible with working filters | Yes |

### Milestone 2: UC-2 MVP + Production (Week 16)

| Criteria | Target | Hard Fail? |
|---|---|---|
| competitive_developments | ≥ 15 projects (LX + Porto) | Yes |
| absorption_rate_model | ≥ 3 quarters historical | Yes |
| location_price_premiums | ≥ 8 significant features | Yes |
| unit_pricing for sample project | Pricing for all units | Yes |
| All daily DAGs succeeding | ≥ 95% success rate (2 weeks) | Yes |
| Data freshness | No source > 2× expected interval | No |
| Documentation | Data dictionary complete | No |

### MVP Hedonic Model Feature Coverage

| Feature | MVP Source | Full Blueprint Source | Accuracy Impact |
|---|---|---|---|
| Area, rooms, bathrooms, floor | S03/S05 listings | Same | None |
| Building age, condition | S03/S05 listings | Same | None |
| Energy class | S03/S05 listing field | S13 ADENE certificates | Minor (~80% populated from listings) |
| Elevator, parking, terrace, pool | S03/S05 listings | Same | None |
| Transport score | S09/S10 OSM | S09/S10 + S24 GTFS | Minor (OSM has stops; GTFS adds frequency) |
| Walkability / POI density | S09 OSM | Same | None |
| Drive-time accessibility | S11 OSRM | Same | None |
| Education score | S22 InfoEscolas (P2) | Same | None (NULL until Sprint 7) |
| Healthcare score | S23 SNS (P2) | Same | None (NULL until Sprint 7) |
| Neighbourhood median price | S01/S03 | Same | None |
| Demographics | S12 Census | Same | None |
| Zoning category | S19 PDM | Same | None |
| **Noise exposure** | **Not available** | S27 noise maps | **~2-3% R² loss in noisy areas** |
| **Flood risk** | **Not available** | S35 APA flood | **~1-2% R² loss in flood zones** |
| **Solar/sun exposure** | **Simplified lookup** | S28 PVGIS | **Negligible** |

**Expected MVP hedonic R²: 0.73-0.78** (vs. 0.78-0.83 full). Sufficient for MVP valuation signals.
