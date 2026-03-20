# House4House

# Portugal Real Estate Data Warehouse — MVP Blueprint
## Complete Technical Architecture: Sources, Stack, Models & Delivery Plan
### Scoped to 31 Data Sources (P0 + P1 + P2) for Minimum Viable Product

---

## Table of Contents

1. Business Use Cases (UC-1, UC-2, UC-3)
2. MVP Data Sources (31 Sources)
3. Technology Stack
4. Infrastructure & Deployment
5. Conceptual Architecture (Medallion Pattern)
6. Data Flows by Source Type
7. Conceptual Data Models
8. Physical Data Models — All Layers
9. Spatial Data Strategy
10. Dependency Graph & Critical Path
11. Orchestration & Scheduling
12. Sprint Plan (10 Sprints / 22 Weeks)
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

### UC-3: Land Development Opportunity Detection

**Users:** Land developers, real estate promoters, investment funds, municipal development offices

**Business Questions:**
- Which plots of land in urban expansion or rehabilitation zones are potentially available for development?
- Under current zoning (CRUS), what can be built on a given plot? (density, height, use type)
- Is the plot inside an ARU (tax benefits for rehabilitation)?
- What SRUP constraints apply? (RAN, REN, DPH, heritage protection)
- What is the current land use (COS)? Is it vacant, agricultural, or already built?
- What cadastral parcels compose the site? What is the total assemblable area?
- Who is the owner? (via NumeroMatriz + Dicofre → Caderneta Predial lookup at Finanças)
- Is there active construction or recent building permits nearby?
- What is the estimated development return (land cost vs. built value at local €/m²)?

**Decision Output:** A ranked list of development sites with a composite score combining buildability, constraint clearance, vacancy status, assemblable area, and estimated development margin.

**What makes a plot a development opportunity:**
- Located in a CRUS urban expansion or urbanizable zone but currently vacant or underutilized (COS non-artificial land use)
- No blocking SRUP constraints (RAN, REN, DPH, heritage protection) — or constraints are manageable
- Assemblable area from contiguous BUPI parcels exceeds minimum viable development size
- Building coverage ratio is low (few or no existing structures per MS Building Footprints)
- Estimated development return (GBA × local €/m² from UC-1 hedonic model minus land + construction cost) exceeds target margin
- Ownership is traceable via NumeroMatriz + Dicofre → Caderneta Predial at Finanças

**Analytical layers needed:**
1. **Vacant/underutilized land detection** — cross-reference COS (non-artificial land use) with CRUS (urban expansion/urbanizable zones) to find mismatches = development opportunity. Validate with building footprints (P1) to confirm no existing structures. Also detect underutilized parcels: low building coverage ratio in prime urban zones.
2. **Buildability assessment** — CRUS zoning parameters (Solo Urbano subcategory) determine what can be built; SRUP constraints determine what cannot
3. **Parcel assembly analysis** — BUPI parcels within opportunity zones, grouped by spatial contiguity using `ST_ClusterDBSCAN` on touching/overlapping parcels, with total area and NumeroMatriz for ownership lookup
4. **ARU overlay** — flag sites inside urban rehabilitation areas for tax benefit eligibility
5. **Construction activity detection** — two-phase approach:
   - *P1: Building footprints* — Microsoft Global ML Building Footprints (~5M polygons for Portugal). Spatial join against BUPI parcels to flag plots with/without existing structures and compute coverage ratio (building area / parcel area).
   - *P2: Sentinel-1 SAR change detection* — cloud-independent radar imagery (C-band, 6-day revisit). Compare backscatter intensity between baseline and current dates; parcels with ΔdB > 3dB = new hard surfaces (construction). Optional coherence analysis to distinguish active construction from completed structures. Access via Copernicus Data Space / Planetary Computer STAC API.
6. **Development economics model** — estimate GBA from zoning params × local €/m² from UC-1 hedonic model, minus estimated land + construction cost. *Dependency: requires UC-1 hedonic model.*
7. **Competition scan** — reuse UC-1's `neighbourhood_market_stats` (nearby active listings and recent transactions) rather than building a separate layer

**Note on ownership:** BUPI provides `NumeroMatriz` + `Dicofre` per parcel → lookup key to **Caderneta Predial** (property tax record at Autoridade Tributária), which contains owner name, fiscal address, assessed tax value (VPT), construction year, and area. The Caderneta is a public document retrievable at any Finanças office or Portal das Finanças. The system identifies the opportunity; the user retrieves ownership for specific plots of interest.

---

## 2. MVP Data Sources (31 Sources)

### 2.1 Scope Decision

This MVP retains **31 data sources** (P0 + P1 + P2) and defers 12 sources (P3 + P4). All deferred fields are nullable in the data models — when P3/P4 sources are added later, the models automatically incorporate them without schema changes.

**Deferred sources and their impact on models:**

| Cut ID | Source | Impact on Models |
|---|---|---|
| S07 | Casa Sapo (third listing portal) | Listings coverage drops ~5-10%; acceptable for MVP |
| S13 | ADENE Energy Certificates | Use `energy_class` from listing data instead; lose kWh/m² detail |
| S21 | INE Building Permits | Promoted to P2 for UC-3 construction activity validation |
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

| # | Data Source | UC-1 | UC-2 | UC-3 | Tier |
|---|---|:---:|:---:|:---:|---|
| S08 | CAOP Boundaries (DGT) | ● | ● | ● | P0 |
| S12 | INE Census 2021 | ● | ● | ○ | P0 |
| S01 | INE — Transaction Prices | ● | ● | ○ | P0 |
| S03 | Idealista — Sale Listings | ● | ● | ○ | P0 |
| S04 | Idealista — Rental Listings | ● | ○ | | P0 |
| S09 | OpenStreetMap — POIs | ● | ● | | P0 |
| S10 | OpenStreetMap — Transport Stops | ● | ● | | P0 |
| S11 | OpenStreetMap — Road Network (OSRM) | ● | ● | | P0 |
| S17 | ECB — Euribor Rates | ● | ● | | P0 |
| S16 | Banco de Portugal (BPStat) | ● | ● | | P0 |
| S05 | Imovirtual — Sale Listings | ● | ● | | P1 |
| S15 | Inside Airbnb | ● | ○ | | P1 |
| S18 | Eurostat — House Price Index | ● | ● | | P1 |
| S19 | PDM Zoning (Lisbon + Porto) | ● | ● | ● | P1 |
| S31 | AT — IMI/IMT Tax Rates | ● | ○ | | P1 |
| S38 | BUPI — Simplified Cadastral Parcels | | | ● | P1 |
| S39 | COS 2023 — Land Use/Cover | ○ | | ● | P1 |
| S40 | CRUS — Vectorized PDM Zoning | ○ | | ● | P1 |
| S41 | SRUP — Property Constraints (IC/RAN/DPH) | ○ | | ● | P1 |
| S42 | MS Building Footprints | | | ● | P1 |
| S44 | Cadastro Predial (Formal Cadastre) | | | ● | P1 |
| S02 | Confidencial Imobiliário (SIR) | ● | ● | | P2 |
| S06 | Imovirtual — Rental Listings | ● | ○ | | P2 |
| S14 | RNAL — AL Licenses | ● | ○ | | P2 |
| S20 | ARU Boundaries | ● | ○ | ● | P2 |
| S21 | INE Building Permits | | | ○ | P2 |
| S22 | InfoEscolas — School Quality | ● | ● | | P2 |
| S23 | SNS — Healthcare Facilities | ● | ● | | P2 |
| S24 | GTFS — Transport Schedules | ● | ● | | P2 |
| S29 | INE — Rental Price Index | ● | ○ | | P2 |
| S34 | Competitive Developments (scraped) | ○ | ● | | P2 |
| S43 | Sentinel-1 SAR Change Detection | | | ○ | P2 |

**Legend:** ● = Critical | ○ = Enrichment

**Note on S19/S40:** S19 (PDM Zoning Lisbon + Porto) is the original MVP source. S40 (CRUS) is the vectorized PDM from DGTERRITÓRIO WFS, covering 5 municipalities (Aveiro, Lisboa, Porto, Coimbra, Leiria). S40 supersedes S19 for covered municipalities — same underlying PDM data, better access mechanism via WFS.

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

**S38 — BUPI Simplified Cadastral Parcels (RGG)**
- **URL:** https://dados.gov.pt/en/datasets/representacao-grafica-georreferenciada/
- **Data:** Georeferenced property boundary polygons from the BUPi simplified cadastral registration system. 3.25M parcels covering 152 municipalities in continental Portugal.
- **Format:** GeoPackage (`.gpkg`) inside a `.zip` archive
- **CRS:** ETRS89 / PT-TM06 — EPSG:3763 (projected, metres)
- **Fields:** ProcessoId, NumeroMatriz (tax matrix number for ownership lookup), Dicofre (6-digit parish code), Concelho, Freguesia, Area_m2
- **Ingestion:** HTTP download → MinIO → PostGIS (GIS ingestion + GPKG bronze templates)
- **Volume:** ~3.25M parcels, ~1.4 GB GPKG
- **Refresh:** Monthly
- **License:** CC-BY 4.0
- **Role:** Critical for UC-3 — parcel assembly, ownership lookup (NumeroMatriz + Dicofre → Caderneta Predial)

**S39 — COS 2023 Land Use/Cover (Carta de Uso e Ocupação do Solo)**
- **URL:** https://dados.gov.pt/en/datasets/carta-de-uso-e-ocupacao-do-solo-cos-serie-2-nova/
- **Data:** National land use/cover classification with 4-level hierarchical nomenclature
- **Format:** GeoPackage (`.gpkg`) inside a `.zip` archive
- **CRS:** ETRS89 / PT-TM06 — EPSG:3763
- **Fields:** COS2023_ID, COS2023_Lg (4-level code), DT, CC, FR, Area_Ha
- **Ingestion:** HTTP download → MinIO → PostGIS (GIS ingestion + GPKG bronze templates)
- **Volume:** ~784K polygons, ~500 MB GPKG
- **Refresh:** ~5 years (next revision ~2028)
- **License:** Open
- **Role:** Critical for UC-3 — vacant land detection (non-artificial land use in urban zones)

**S40 — CRUS Vectorized PDM Zoning**
- **URL:** DGT WFS (SDISNITWFS endpoints per municipality)
- **Data:** Vectorized PDM (Plano Director Municipal) zoning from CRUS — Solo Urbano/Rústico classification with subcategories
- **Format:** GeoJSON via WFS 2.0.0
- **CRS:** ETRS89 / PT-TM06 — EPSG:3763
- **Coverage:** 5 municipalities (Aveiro, Lisboa, Porto, Coimbra, Leiria)
- **Ingestion:** WFS GetFeature → GeoJSON → MinIO → PostGIS
- **Volume:** ~5K zone polygons, ~100 MB
- **Refresh:** Static (PDM revision ~every 10 years)
- **Note:** Supersedes S19 for covered municipalities — same underlying PDM data, WFS access
- **Role:** Critical for UC-3 — buildability assessment (what can be built where)

**S41 — SRUP Property Constraints (Servidões e Restrições de Utilidade Pública)**
- **URL:** DGT WFS (SRUP_IC, SRUP_RAN, SRUP_DPH endpoints)
- **Data:** Property easements and restrictions — heritage sites (IC), agricultural reserve (RAN), public water domain (DPH)
- **Format:** GeoJSON via WFS 2.0.0
- **CRS:** EPSG:4326 (WGS84)
- **Ingestion:** WFS GetFeature → GeoJSON → MinIO → PostGIS (per category)
- **Volume:** ~3,676 IC features, ~268 RAN features, ~7 DPH features
- **Refresh:** Ad-hoc
- **Role:** Critical for UC-3 — constraint overlay (what cannot be built); enrichment for UC-1

**S42 — Microsoft Global ML Building Footprints**
- **URL:** https://github.com/microsoft/GlobalMLBuildingFootprints
- **Data:** Building polygons for Portugal, ML-extracted from aerial/satellite imagery
- **Format:** GeoJSON partitioned by country; also available via Overture Maps
- **CRS:** EPSG:4326 (WGS84)
- **Ingestion:** HTTP download → MinIO → PostGIS
- **Volume:** ~5M building polygons for Portugal, ~1.5-2 GB
- **Refresh:** Annual
- **License:** ODbL
- **Quality note:** ML-extracted footprints may have false positives (shadows, containers) and false negatives (small structures). Acceptable for screening; specific sites should be verified with aerial imagery.
- **Role:** Critical for UC-3 — vacant plot detection, building coverage ratio per parcel

**S44 — Cadastro Predial (Formal Cadastre)**
- **URL:** DGT OGC API (country-wide, partial coverage)
- **Data:** Official surveyed property parcel boundaries (higher accuracy than BUPI)
- **Format:** GeoJSON via OGC API Features
- **CRS:** ETRS89 / PT-TM06 — EPSG:3763
- **Ingestion:** OGC API → GeoJSON → MinIO → PostGIS
- **Volume:** Partial coverage (~50% of municipalities)
- **Refresh:** Ad-hoc
- **Role:** Enrichment for UC-3 — validates BUPI boundaries for specific sites of interest

#### P2 — Enhancement (11 sources)

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

**S21 — INE Building Permits**
- **URL:** https://www.ine.pt (API)
- **Data:** Licensed construction activity by municipality — new buildings, renovations, demolitions
- **Format:** JSON (API)
- **Ingestion:** REST API → Bronze (same pipeline as S01)
- **Volume:** ~50K records
- **Refresh:** Monthly
- **Role:** UC-3 — active construction validation; building permit counts near opportunity sites

**S43 — Sentinel-1 SAR Change Detection**
- **URL:** Copernicus Data Space (https://dataspace.copernicus.eu) / Microsoft Planetary Computer (STAC API)
- **Data:** C-band SAR radar imagery, 5×20m resolution, 6-day revisit cycle, cloud-independent
- **Processing:** Backscatter change detection (ΔdB between baseline and current dates) + optional InSAR coherence analysis. Per-parcel zonal statistics against BUPI geometries.
- **Pipeline:** rasterio/SNAP + Python zonal stats → PostGIS (runs outside dbt)
- **Volume:** Per-parcel flags (~50 MB processed output)
- **Refresh:** Monthly (or on-demand)
- **Role:** UC-3 — active construction detection; parcels with ΔdB > 3dB indicate new hard surfaces

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
| **Viz: Spatial** | QGIS + Kepler.gl | 3.34 / 3.0 | Spatial analysis (QGIS) and interactive map visualization (Kepler.gl embedded in Streamlit via `streamlit-keplergl`). |
| **Viz: Custom** | Streamlit | 1.30+ | Host for Kepler.gl maps + custom apps — property valuator, pricing simulator, site analyzer. |
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

  # ── Visualization & Serving ──
  metabase:
    image: metabase/metabase:v0.48.0
    depends_on:
      - postgres
    ports:
      - "3000:3000"
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase
      MB_DB_PORT: 5432
      MB_DB_USER: metabase
      MB_DB_PASS: ${METABASE_DB_PASSWORD}
      MB_DB_HOST: postgres

  streamlit:
    build:
      context: ./apps
      dockerfile: Dockerfile
    depends_on:
      - postgres
    ports:
      - "8501:8501"
    environment:
      DATABASE_URL: postgres://streamlit:${STREAMLIT_DB_PASSWORD}@postgres:5432/re_warehouse

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
│  │                                                                 │       │
│  │  ┌─────────────────────────────────────────────────────────┐    │       │
│  │  │  UC-3: LAND DEVELOPMENT OPPORTUNITIES                   │    │       │
│  │  │                                                         │    │       │
│  │  │  parcel_buildability ──── zoning + constraints overlay   │    │       │
│  │  │  development_sites ──── opportunity scoring              │    │       │
│  │  │  site_parcels ──── BUPI parcel assembly                  │    │       │
│  │  │          │                                              │    │       │
│  │  │          ▼                                              │    │       │
│  │  │  ┌────────────────────────────────────────────────┐     │    │       │
│  │  │  │  development_sites (materialized table)        │     │    │       │
│  │  │  │  Composite opportunity_score per site           │     │    │       │
│  │  │  └────────────────────────────────────────────────┘     │    │       │
│  │  └─────────────────────────────────────────────────────────┘    │       │
│  └─────────────────────────────────────────────────────────────────┘       │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SERVING LAYER                                             │
│                                                                             │
│  ┌────────────────────┐  ┌──────────────────────────────┐                  │
│  │ Metabase :3000     │  │ Streamlit :8501               │                  │
│  │ Investment board    │  │ Property Valuator (UC-1)      │                  │
│  │ Pricing dashboard  │  │ Pricing Simulator (UC-2)      │                  │
│  │ Land opportunities │  │ Site Analyzer (UC-3)          │                  │
│  │ KPIs, tables,      │  │ ┌──────────────────────────┐ │                  │
│  │ charts, filters    │  │ │ Kepler.gl (embedded)     │ │                  │
│  └────────────────────┘  │ │ Investment Map (UC-1)    │ │                  │
│                           │ │ Parcel Explorer (UC-3)   │ │                  │
│  ┌────────────────────┐  │ │ Opportunity Heatmap(UC-3)│ │                  │
│  │ QGIS               │  │ └──────────────────────────┘ │                  │
│  │ Spatial analysis   │  └──────────────────────────────┘                  │
│  └────────────────────┘                                                    │
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

### Flow E: Spatial Analysis (UC-3 Land Opportunities)
```
COS (land use) + CRUS (zoning) + SRUP (constraints) + BUPI (parcels) + Building Footprints
  → stg_* (staging views — CRS alignment to EPSG:3763)
    → silver_geo.parcel_buildability (pre-filtered to CRUS municipality extents)
      → ST_ClusterDBSCAN (parcel contiguity grouping)
        → gold_analytics.development_sites (opportunity scoring)
        → gold_analytics.site_parcels (parcel-to-site mapping)

CRS alignment strategy:
  - BUPI, COS, CRUS, Cadastro: native EPSG:3763 (no transform needed)
  - SRUP IC/RAN/DPH, Building Footprints: EPSG:4326 → ST_Transform to 3763 at staging
  - All spatial joins performed in EPSG:3763 (projected, metres — accurate area/distance)
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

### 7.5 UC-3 Conceptual Model: Land Development Opportunities

```
                    ┌─────────────────────┐
                    │   DEVELOPMENT SITE  │
                    │   (opportunity)     │
                    └──────────┬──────────┘
                               │
       ┌───────────────┬───────┼───────┬───────────────┐
       │               │       │       │               │
┌──────┴───────┐ ┌─────┴─────┐ │ ┌─────┴─────┐ ┌──────┴───────┐
│ BUILDABILITY │ │  PARCELS  │ │ │ ECONOMICS │ │ CONSTRUCTION │
│              │ │  (BUPI)   │ │ │           │ │  ACTIVITY    │
│ zone_categ   │ │           │ │ │ total_area│ │              │
│ land_class   │ │ process_id│ │ │ est_gba   │ │ has_building │
│ is_urban_exp │ │ matrix_num│ │ │ local_€m2 │ │ coverage_%   │
│ srup_flags   │ │ dicofre   │ │ │ est_rev   │ │ sar_delta_db │
│ ren_overlap  │ │ area_m2   │ │ │ est_cost  │ │ is_active    │
│ is_aru       │ │ owner_key │ │ │ est_margin│ │ permit_flag  │
└──────────────┘ └───────────┘ │ └───────────┘ └──────────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
         ┌──────┴───────┐ ┌───┴──────┐ ┌─────┴──────┐
         │  LAND USE    │ │ BUILDING │ │ COMPETITION│
         │  (COS)       │ │ FOOTPRINT│ │  (UC-1)    │
         │ cos_level_1  │ │ (MS)     │ │            │
         │ is_vacant    │ │          │ │ nearby_lst │
         │ is_agri      │ │ bldg_area│ │ recent_txn │
         │ is_built     │ │ bldg_cnt │ │ avg_eur_m2 │
         └──────────────┘ └──────────┘ └────────────┘
```

**Key relationships:**
- Each **development site** is composed of one or more contiguous **BUPI parcels** (grouped via `ST_ClusterDBSCAN`)
- **Buildability** is determined by CRUS zoning (what can be built) intersected with SRUP constraints (what cannot)
- **Land use** from COS 2023 detects vacant/underutilized parcels in urban zones
- **Building footprints** (MS) validate vacancy and compute building coverage per parcel
- **Economics** reuses UC-1's hedonic model for local €/m² estimates
- **Construction activity** (P2) uses Sentinel-1 SAR change detection for cloud-independent monitoring

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

Source-oriented: stores scraped JSON fields as-is in TEXT columns. JSONB for nested
arrays (features, equipment, images). No parsing at bronze — type casting, area
extraction, and feature flags are silver/dbt work.

```sql
CREATE TABLE bronze_listings.raw_idealista (
    id                    BIGSERIAL PRIMARY KEY,

    -- Metadata
    _scrape_date          DATE NOT NULL,
    _batch_id             VARCHAR(50),
    _minio_path           TEXT,                           -- Path to raw JSON in MinIO
    _ingested_at          TIMESTAMPTZ DEFAULT NOW(),
    _source               VARCHAR(30) DEFAULT 'idealista',
    _carried_forward      BOOLEAN DEFAULT FALSE,          -- TRUE if listing unchanged since last scrape

    -- Internal keys (derived during load for indexing)
    _property_id          TEXT,                           -- Normalised property ID
    _distrito             TEXT,                           -- District name (for partitioning)
    _operation            TEXT,                           -- 'sale' or 'rent'

    -- Property identifiers (raw from scraper)
    property_id           TEXT,
    property_url          TEXT,
    property_type         TEXT,                           -- e.g. 'Apartamento', 'Moradia'
    property_subtype      TEXT,

    -- Price (raw text — may contain formatting)
    property_price        TEXT,                           -- e.g. '250.000 €'
    price_currency_symbol TEXT,

    -- Areas (raw text)
    lot_size              TEXT,
    lot_size_usable       TEXT,
    property_dimensions   TEXT,                           -- e.g. '85 m²'

    -- Rooms (raw text)
    bedroom_count         TEXT,
    bedrooms_count        TEXT,                           -- Alternate field name from scraper
    bathroom_count        TEXT,

    -- Floor (raw text)
    floor                 TEXT,
    floor_description     TEXT,

    -- Features / equipment (JSONB arrays from scraper)
    property_features     JSONB,                          -- e.g. ["Elevator", "Parking", "Terrace"]
    property_equipment    JSONB,                          -- e.g. ["Air Conditioning", "Central Heating"]

    -- Images (JSONB arrays)
    property_images       JSONB,                          -- URLs
    property_image_tags   JSONB,                          -- AI-generated tags per image

    -- Property details (raw text)
    property_condition    TEXT,
    property_description  TEXT,                           -- Full listing description (Portuguese)
    property_title        TEXT,
    energy_certificate    TEXT,
    address               TEXT,
    location_name         TEXT,

    -- Location
    location_hierarchy    JSONB,                          -- Nested hierarchy from scraper
    latitude              NUMERIC(10,7),
    longitude             NUMERIC(10,7),
    country               TEXT,

    -- Agency
    agency_name           TEXT,
    agency_phone          TEXT,
    agency_logo           TEXT,

    -- Timestamps / status (raw)
    modified_at           BIGINT,                         -- Unix timestamp from API
    status                TEXT,
    last_deactivated_at   TEXT,
    operation             TEXT
);
CREATE INDEX idx_idealista_property_id ON bronze_listings.raw_idealista(_property_id);
CREATE INDEX idx_idealista_scrape_date ON bronze_listings.raw_idealista(_scrape_date);
CREATE INDEX idx_idealista_operation ON bronze_listings.raw_idealista(_operation, _scrape_date);
CREATE INDEX idx_idealista_distrito ON bronze_listings.raw_idealista(_distrito);

-- S05/S06 Imovirtual: similar source-oriented schema (not yet implemented)
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

#### OSM — OpenStreetMap (S11)

Source is a Geofabrik Portugal PBF extract, pre-processed into shapefiles. 14 tables in
`bronze_location` loaded source-faithful via ogr2ogr. All share a common base schema
(osm_id, code, fclass, name, geom) with layer-specific extras.

```sql
-- Common columns across all OSM layers:
--   osm_id    TEXT         — OpenStreetMap feature ID
--   code      INTEGER      — Geofabrik numeric feature code
--   fclass    TEXT         — Feature class (e.g. 'restaurant', 'bus_stop', 'primary')
--   name      TEXT         — Feature name (may be NULL)
--   geom      GEOMETRY     — EPSG:4326 (WGS84)
--   _load_timestamp TIMESTAMPTZ DEFAULT NOW()

-- Points of interest (POIs + POFWs)
-- raw_osm_pois         174K  POINT          — Restaurants, shops, ATMs, pharmacies, ...
-- raw_osm_pois_a       130K  MULTIPOLYGON   — Same as above (area features)
-- raw_osm_pofw         1.7K  POINT          — Places of worship
-- raw_osm_pofw_a       11K   MULTIPOLYGON

-- Transport
-- raw_osm_transport    49K   POINT          — Bus stops, train stations, ferry terminals
-- raw_osm_transport_a  1.1K  MULTIPOLYGON
-- raw_osm_railways     11K   LINESTRING     — + layer, bridge, tunnel
-- raw_osm_roads        1.5M  LINESTRING     — + ref, oneway, maxspeed, layer, bridge, tunnel
-- raw_osm_traffic      172K  POINT          — Traffic signals, crossings, speed cameras
-- raw_osm_traffic_a    60K   MULTIPOLYGON

-- Land & water
-- raw_osm_buildings_a  2.1M  MULTIPOLYGON   — + type
-- raw_osm_landuse_a    492K  MULTIPOLYGON
-- raw_osm_natural      227K  POINT
-- raw_osm_natural_a    1.6K  MULTIPOLYGON
-- raw_osm_places       31K   POINT          — + population
-- raw_osm_places_a     694   MULTIPOLYGON   — + population
-- raw_osm_water_a      56K   MULTIPOLYGON
-- raw_osm_waterways    119K  LINESTRING     — + width
```

#### Macro Sources (S16 BPStat, S17 ECB, S18 Eurostat)

```sql
-- ── raw_bpstat: Banco de Portugal (S16) ──────────────────────────────────────
-- 3 domains, 16 datasets, ~130 series, ~24K rows.
-- Source: JSON-stat 2.0 API. One row per (series × observation period).
-- Flattened from JSON-stat cube: extension.series → dimension positions → values.

CREATE TABLE bronze_macro.raw_bpstat (
    id                   BIGSERIAL PRIMARY KEY,
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'bpstat',
    _batch_id            VARCHAR(50),

    -- Dataset identity
    domain_id            INTEGER,                         -- BPStat domain (186, 21, 39)
    dataset_id           VARCHAR(50),                     -- Dataset hash (e.g. 'd45bb68e...')

    -- Series identity
    series_id            INTEGER NOT NULL,                -- Unique series ID from extension.series
    series_name          TEXT,                            -- Full label (includes dimension breakdown)

    -- Observation
    period               VARCHAR(20) NOT NULL,            -- End-of-period date (e.g. '2024-12-31')
    value                NUMERIC(20,6),                   -- Numeric value as-is from API
    unit                 VARCHAR(100),                    -- From metric dimension (e.g. 'Percentage', 'Millions of euros')
    status               VARCHAR(10)                      -- Quality flag ('F' = final)
);
CREATE INDEX idx_bpstat_series_id ON bronze_macro.raw_bpstat(series_id);
CREATE INDEX idx_bpstat_dataset ON bronze_macro.raw_bpstat(dataset_id);
CREATE INDEX idx_bpstat_series_period ON bronze_macro.raw_bpstat(series_id, period);

-- ── raw_ecb: European Central Bank (S17) ─────────────────────────────────────
-- 3 Euribor series (3M, 6M, 12M), ~1.2K rows.
-- Source: SDMX-JSON API. One row per (series × time_period).
-- Flattened from dataSets[0].series[key].observations.

CREATE TABLE bronze_macro.raw_ecb (
    id                   BIGSERIAL PRIMARY KEY,
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'ecb',
    _batch_id            VARCHAR(50),

    -- Series identity
    series_key           VARCHAR(100) NOT NULL,           -- SDMX dimension key (e.g. 'M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA')
    series_name          TEXT,                            -- Full label from structure.dimensions.series

    -- Observation
    time_period          VARCHAR(10) NOT NULL,            -- Month string (e.g. '2024-01')
    value                NUMERIC(12,7),                   -- Interest rate (e.g. 2.0113)
    unit                 VARCHAR(50),                     -- From series attributes (e.g. 'PCPA' = percent per annum)
    obs_status           VARCHAR(10),                     -- Observation status (e.g. 'A' = normal)
    obs_conf             VARCHAR(10)                      -- Observation confidentiality
);
CREATE INDEX idx_ecb_series_key ON bronze_macro.raw_ecb(series_key);
CREATE INDEX idx_ecb_series_period ON bronze_macro.raw_ecb(series_key, time_period);

-- ── raw_eurostat: Eurostat HPI (S18) ─────────────────────────────────────────
-- 1 dataset (PRC_HPI_Q), 38 EU countries, ~31K rows.
-- Source: JSON-stat 2.0 API. One row per (freq × purchase × unit × geo × time).
-- Flattened from pure dimensional cube (no extension.series — unlike BPStat).

CREATE TABLE bronze_macro.raw_eurostat (
    id                   BIGSERIAL PRIMARY KEY,
    _ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    _source              VARCHAR(30) DEFAULT 'eurostat',
    _batch_id            VARCHAR(50),

    -- Dataset identity
    dataset_code         VARCHAR(30) NOT NULL,            -- 'prc_hpi_q'

    -- Dimensions (from JSON-stat cube)
    freq                 CHAR(1) DEFAULT 'Q',             -- Always 'Q' (Quarterly)
    purchase             VARCHAR(20) NOT NULL,             -- TOTAL, DW_NEW (new), DW_EXST (existing)
    unit                 VARCHAR(20) NOT NULL,             -- I15_Q (index 2015=100), RCH_A (annual %), RCH_Q (quarterly %), I10_Q (index 2010=100)
    geo                  VARCHAR(10) NOT NULL,             -- ISO country code or aggregate (PT, ES, EU, EA, ...)
    time_period          VARCHAR(10) NOT NULL,             -- Quarter string (e.g. '2024-Q1')

    -- Observation
    value                NUMERIC(12,4),                   -- Index value or rate of change (depends on unit)
    status               VARCHAR(10)                      -- Quality flag: p=provisional, b=break, d=differs, e=estimated
);
CREATE INDEX idx_eurostat_geo_time ON bronze_macro.raw_eurostat(geo, time_period);
CREATE INDEX idx_eurostat_dataset ON bronze_macro.raw_eurostat(dataset_code);
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

#### Regulatory & Cadastral Sources (S38-S44)

```sql
-- S38 — BUPI Simplified Cadastral Parcels (~3,250,000 rows)
-- Source: dados.gov.pt GeoPackage, EPSG:3763, monthly refresh
-- Fields: processoid (BUPi ID), numeromatriz (tax matrix → ownership lookup),
--         dicofre (6-digit parish code), concelho, freguesia, area_m2
CREATE TABLE bronze_regulatory.raw_bupi (
    processoid      INTEGER,
    numeromatriz    TEXT,
    dicofre         VARCHAR(6),
    concelho        TEXT,
    freguesia       TEXT,
    area_m2         DOUBLE PRECISION,
    geom            GEOMETRY(MULTIPOLYGON, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ
);
CREATE INDEX idx_raw_bupi_geom ON bronze_regulatory.raw_bupi USING GIST(geom);
CREATE INDEX idx_raw_bupi_dicofre ON bronze_regulatory.raw_bupi(dicofre);
CREATE INDEX idx_raw_bupi_concelho ON bronze_regulatory.raw_bupi(concelho);

-- S39 — COS 2023 Land Use/Cover (~784,000 rows)
-- Source: dados.gov.pt GeoPackage, EPSG:3763, ~5-year refresh
-- Fields: cos2023_lg (4-level hierarchical code), dt/cc/fr (admin codes), area_ha
CREATE TABLE bronze_geo.raw_cos2023 (
    cos2023_id      INTEGER,
    cos2023_lg      TEXT,
    dt              TEXT,
    cc              TEXT,
    fr              TEXT,
    area_ha         DOUBLE PRECISION,
    geom            GEOMETRY(MULTIPOLYGON, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ
);
CREATE INDEX idx_raw_cos2023_geom ON bronze_geo.raw_cos2023 USING GIST(geom);
CREATE INDEX idx_raw_cos2023_lg ON bronze_geo.raw_cos2023(cos2023_lg);

-- S40 — CRUS Vectorized PDM Zoning (~5,000 rows, 5 municipalities)
-- Source: DGT WFS, EPSG:3763, static (PDM revision ~10yr)
-- Supersedes S19 for covered municipalities
CREATE TABLE bronze_regulatory.raw_crus_ordenamento (
    id              TEXT,
    municipio       TEXT,
    categoria       TEXT,
    subcategoria    TEXT,
    area_ha         DOUBLE PRECISION,
    geom            GEOMETRY(MULTIPOLYGON, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ
);
CREATE INDEX idx_raw_crus_geom ON bronze_regulatory.raw_crus_ordenamento USING GIST(geom);
CREATE INDEX idx_raw_crus_municipio ON bronze_regulatory.raw_crus_ordenamento(municipio);
CREATE INDEX idx_raw_crus_cat ON bronze_regulatory.raw_crus_ordenamento(municipio, categoria);

-- S41 — SRUP Heritage Sites IC (~3,676 rows)
-- Source: DGT WFS, EPSG:4326 (GEOMETRYCOLLECTION — staging transforms to 3763)
CREATE TABLE bronze_regulatory.raw_srup_ic (
    id              TEXT,
    designacao      TEXT,
    classificacao   TEXT,
    municipios      TEXT,
    servidao        TEXT,
    area_ha         DOUBLE PRECISION,
    geom            GEOMETRY(GEOMETRYCOLLECTION, 4326),
    _feature_type   TEXT,
    _load_timestamp TIMESTAMPTZ
);

-- S41 — SRUP Agricultural Reserve RAN (~268 rows)
CREATE TABLE bronze_regulatory.raw_srup_ran (
    id              TEXT,
    concelho        TEXT,
    dinamica        TEXT,
    servidao        TEXT,
    geom            GEOMETRY(GEOMETRYCOLLECTION, 4326),
    _feature_type   TEXT,
    _load_timestamp TIMESTAMPTZ
);

-- S41 — SRUP Public Water Domain DPH (~7 rows)
CREATE TABLE bronze_regulatory.raw_srup_dph (
    id              TEXT,
    designacao      TEXT,
    municipios      TEXT,
    servidao        TEXT,
    area_ha         DOUBLE PRECISION,
    geom            GEOMETRY(GEOMETRYCOLLECTION, 4326),
    _feature_type   TEXT,
    _load_timestamp TIMESTAMPTZ
);

-- S44 — Cadastro Predial / Formal Cadastre (partial coverage)
-- Source: DGT OGC API, EPSG:3763
CREATE TABLE bronze_regulatory.raw_cadastro (
    objectid        INTEGER,
    ipr             TEXT,
    secao           TEXT,
    parcela         TEXT,
    dicofre         VARCHAR(6),
    area_m2         DOUBLE PRECISION,
    geom            GEOMETRY(MULTIPOLYGON, 3763),
    _source_url     TEXT,
    _load_timestamp TIMESTAMPTZ
);
CREATE INDEX idx_raw_cadastro_geom ON bronze_regulatory.raw_cadastro USING GIST(geom);
CREATE INDEX idx_raw_cadastro_dicofre ON bronze_regulatory.raw_cadastro(dicofre);

-- S42 — MS Building Footprints (~5M rows, P1 — not yet ingested)
-- Source: GitHub/Overture Maps, EPSG:4326, ML-extracted from aerial imagery
CREATE TABLE bronze_geo.raw_building_footprints (
    bf_id           SERIAL PRIMARY KEY,
    height          DOUBLE PRECISION,
    confidence      DOUBLE PRECISION,
    geom            GEOMETRY(POLYGON, 4326),
    _source         TEXT,
    _load_timestamp TIMESTAMPTZ
);
CREATE INDEX idx_raw_bf_geom ON bronze_geo.raw_building_footprints USING GIST(geom);

-- S43 — Sentinel-1 SAR Change Detection (P2 — not yet ingested)
-- Per-parcel backscatter change metrics. No redundant geometry — uses processoid FK to raw_bupi.
-- Pipeline: rasterio/SNAP + Python zonal stats → PostGIS (runs outside dbt)
CREATE TABLE bronze_geo.raw_sar_change (
    sar_id              SERIAL PRIMARY KEY,
    processoid          INTEGER,
    dicofre             VARCHAR(6),
    baseline_date       DATE,
    current_date        DATE,
    orbit_direction     TEXT,
    mean_backscatter_db DOUBLE PRECISION,
    delta_db            DOUBLE PRECISION,
    coherence           DOUBLE PRECISION,
    pixel_count         INTEGER,
    _pipeline_run       TEXT,
    _load_timestamp     TIMESTAMPTZ
);
CREATE INDEX idx_raw_sar_processoid ON bronze_geo.raw_sar_change(processoid);
CREATE INDEX idx_raw_sar_dicofre ON bronze_geo.raw_sar_change(dicofre);
```

### 8.3 Silver Layer — Cleaned, Conformed, Geocoded

#### Unified Listings (anchor table for all property analysis)

```sql
-- dbt transforms: parse TEXT bronze columns to typed silver columns, geocode addresses.
--
-- Bronze → Silver mapping (Idealista source-oriented bronze):
--   property_url TEXT           → listing_url TEXT, source_listing_id (extracted from URL)
--   property_price TEXT         → price_eur NUMERIC (parse "€ 350,000" → 350000.00)
--   property_type TEXT          → property_type_key INTEGER (map to dim_property_type)
--   property_typology TEXT      → typology VARCHAR, num_rooms SMALLINT (parse "T3" → 3)
--   property_size TEXT          → useful_area_m2 NUMERIC (parse "120 m²" → 120.00)
--   property_condition TEXT     → condition VARCHAR (normalize labels)
--   property_location TEXT      → address_clean TEXT, geocode → lat/lon/freguesia
--   detail_json JSONB           → gross_area_m2, plot_area_m2, num_bathrooms, floor_number,
--                                  construction_year, energy_class, has_elevator, has_parking, ...
--   features_json JSONB         → has_terrace, has_garden, has_pool (flag extraction)
--   scrape_date DATE            → first_seen_date, last_seen_date (SCD logic)
--
-- All type casting and business logic belongs in dbt (silver), NOT in bronze.

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
-- Bronze → Silver mapping:
--   raw_bgri: subsection-level census rows (variable_code + value per subsecção)
--     Aggregated to freguesia level via BGRI hierarchy (subsecção → secção → freguesia)
--     variable_code pivot: N_INDIVIDUOS → total_population, N_ALOJAMENTOS → total_dwellings, etc.
--     Spatial join with dim_geography via freguesia_code → geo_key
--   raw_ine_indicators: additional computed metrics (aging_index, vacancy_rate, etc.)

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
-- Bronze → Silver mapping:
--   raw_osm_transport: osm_id TEXT → (not stored), name TEXT → stop_name,
--     fclass TEXT → stop_type (mapped: 'railway_station' → 'rail', 'bus_stop' → 'bus', etc.)
--     geom GEOMETRY → geom + geom_pt (reproject to 3763), spatial join → geo_key
--   GTFS (future S24): route_count, service_frequency, operator, is_interchange

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

-- Bronze → Silver mapping:
--   raw_osm_pois: osm_id TEXT → osm_id BIGINT (cast), name TEXT → name,
--     fclass TEXT → fclass + category (grouped: 'restaurant' → 'food', 'pharmacy' → 'health', etc.)
--     geom GEOMETRY → geom + geom_pt (reproject to 3763), spatial join → geo_key

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
-- Unified time-series from all bronze macro sources.
-- dbt transforms: parse periods to DATE, compute change rates, conform codes.
--
-- Bronze → Silver mapping:
--   raw_bpstat  → indicator_code = 'BPSTAT_{series_id}', period parsed to DATE
--   raw_ecb     → indicator_code = series_key, time_period parsed to DATE
--   raw_eurostat → indicator_code = 'EUROSTAT_{purchase}_{unit}', geo = country code
--
-- Eurostat rows carry geo (PT, ES, EU, ...) for cross-country comparison.
-- BPStat and ECB are Portugal-only (geo = 'PT').

CREATE TABLE silver_market.macro_timeseries (
    id                   BIGSERIAL PRIMARY KEY,
    indicator_code       VARCHAR(100) NOT NULL,            -- Conformed code (e.g. 'BPSTAT_12710732', 'EUROSTAT_TOTAL_I15_Q')
    indicator_name       VARCHAR(300) NOT NULL,            -- Human-readable label
    category             VARCHAR(50) NOT NULL,             -- housing_prices, interest_rates, housing_credit, euribor
    source               VARCHAR(30) NOT NULL,             -- 'bpstat', 'ecb', 'eurostat'
    geo                  VARCHAR(10) DEFAULT 'PT',         -- ISO country code (PT for national sources, varies for Eurostat)
    observation_date     DATE NOT NULL,                    -- Parsed from period/time_period
    period_type          VARCHAR(10),                      -- 'M' (monthly), 'Q' (quarterly)
    value                NUMERIC(20,6),
    unit                 VARCHAR(100),
    mom_change           NUMERIC(10,4),                    -- Month-on-month % (computed in dbt)
    qoq_change           NUMERIC(10,4),                    -- Quarter-on-quarter %
    yoy_change           NUMERIC(10,4),                    -- Year-on-year %
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_macro_ind ON silver_market.macro_timeseries(indicator_code, observation_date);
CREATE INDEX idx_macro_geo ON silver_market.macro_timeseries(geo, observation_date);

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

#### Geo & Regulatory (UC-3 foundation)

```sql
-- silver_geo.land_use — COS 2023 enriched with hierarchy and boolean flags (~784K rows)
-- Source: stg_cos2023 + COS nomenclature hierarchy lookup
-- Materialization: dbt table
CREATE TABLE silver_geo.land_use (
    land_use_key         BIGSERIAL PRIMARY KEY,
    id                   INTEGER NOT NULL,
    land_use_code        TEXT NOT NULL,           -- COS 4-level code (e.g. "1.1.1.01")
    land_use_label       TEXT,
    area_ha              DOUBLE PRECISION,
    land_use_level1      TEXT,                    -- Level 1 (e.g. "Territórios artificializados")
    land_use_level2      TEXT,                    -- Level 2
    land_use_level3      TEXT,                    -- Level 3
    land_use_category    TEXT,                    -- Grouped category
    is_urban             BOOLEAN,
    is_residential       BOOLEAN,
    is_agricultural      BOOLEAN,
    is_forest            BOOLEAN,
    freguesia_code       TEXT,
    concelho_code        TEXT,
    distrito_code        TEXT,
    geom                 GEOMETRY(MULTIPOLYGON, 3763),
    geom_wgs84           GEOMETRY(MULTIPOLYGON, 4326),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_land_use_geom ON silver_geo.land_use USING GIST(geom);
CREATE INDEX idx_land_use_code ON silver_geo.land_use(land_use_code);

-- silver_geo.zoning — CRUS PDM zoning enriched (~5K rows, 5 municipalities)
-- Source: stg_crus_ordenamento
-- Materialization: dbt table
CREATE TABLE silver_geo.zoning (
    zone_key             BIGSERIAL PRIMARY KEY,
    municipality_code    TEXT,
    municipality_name    TEXT NOT NULL,
    land_classification  TEXT,                    -- Solo Urbano / Solo Rústico
    land_category        TEXT,                    -- Subcategory
    land_designation     TEXT,                    -- Detailed designation
    zone_category        TEXT,                    -- Grouped zone type
    area_ha              DOUBLE PRECISION,
    pdm_publication_date DATE,
    geom                 GEOMETRY(MULTIPOLYGON, 3763),
    geom_wgs84           GEOMETRY(MULTIPOLYGON, 4326),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_zoning_geom ON silver_geo.zoning USING GIST(geom);
CREATE INDEX idx_zoning_municipality ON silver_geo.zoning(municipality_name);

-- silver_geo.building_footprints — MS Building Footprints cleaned (P1 — not yet ingested)
-- Source: stg_building_footprints (ST_Transform from 4326 to 3763)
CREATE TABLE silver_geo.building_footprints (
    bf_id                INTEGER PRIMARY KEY,
    area_m2              DOUBLE PRECISION,
    height               DOUBLE PRECISION,        -- nullable
    confidence           DOUBLE PRECISION,
    geom_pt              GEOMETRY(POLYGON, 3763),
    geom_4326            GEOMETRY(POLYGON, 4326),
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_bf_geom_pt ON silver_geo.building_footprints USING GIST(geom_pt);

-- silver_geo.parcel_buildability — UC-3 core model
-- Each BUPI parcel enriched with zoning, land use, constraints, and building coverage.
-- Pre-filtered to CRUS municipality extents (~500K of 3.25M parcels).
-- Materialization: dbt TABLE (not view) — estimated refresh ~15-20 min.
-- Spatial join strategy: filter BUPI to ST_Within(crus_extent), then LEFT JOIN against
--   zoning (centroid), land_use (largest overlap), SRUP (ST_Intersects), footprints (area ratio)
CREATE TABLE silver_geo.parcel_buildability (
    process_id           INTEGER NOT NULL,
    dicofre              VARCHAR(6) NOT NULL,
    matrix_number        TEXT,
    parish               TEXT,
    municipality         TEXT,
    parcel_area_m2       DOUBLE PRECISION,
    geom_pt              GEOMETRY(MULTIPOLYGON, 3763),
    geom_4326            GEOMETRY(MULTIPOLYGON, 4326),
    -- Zoning (from CRUS spatial join)
    zone_category        TEXT,                    -- Solo Urbano / Solo Rústico
    zone_subcategory     TEXT,
    is_urban             BOOLEAN,
    is_urban_expansion   BOOLEAN,
    is_rural             BOOLEAN,
    -- Land use (from COS spatial join)
    cos_level_1          TEXT,
    cos_level_2          TEXT,
    is_vacant            BOOLEAN,
    is_agricultural      BOOLEAN,
    is_built             BOOLEAN,
    -- Constraints (from SRUP spatial joins)
    srup_ran_flag        BOOLEAN DEFAULT FALSE,
    srup_dph_flag        BOOLEAN DEFAULT FALSE,
    srup_ic_flag         BOOLEAN DEFAULT FALSE,
    srup_ren_flag        BOOLEAN DEFAULT FALSE,   -- P2 (REN not yet ingested)
    -- Building coverage (from footprints spatial join)
    has_building         BOOLEAN,
    building_count       INTEGER DEFAULT 0,
    building_coverage_pct NUMERIC(5,4),           -- 0.0000 to 1.0000
    -- ARU (P2)
    is_aru               BOOLEAN DEFAULT FALSE,
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pb_geom ON silver_geo.parcel_buildability USING GIST(geom_pt);
CREATE INDEX idx_pb_dicofre ON silver_geo.parcel_buildability(dicofre);
CREATE INDEX idx_pb_municipality ON silver_geo.parcel_buildability(municipality);

-- silver_geo.parcel_construction_activity — construction signals per parcel (P2)
-- Source: stg_bupi JOIN stg_sar_change + stg_building_permits
CREATE TABLE silver_geo.parcel_construction_activity (
    process_id           INTEGER NOT NULL,
    dicofre              VARCHAR(6),
    sar_delta_db         DOUBLE PRECISION,        -- backscatter change
    sar_coherence        DOUBLE PRECISION,        -- InSAR coherence (0-1)
    sar_is_active        BOOLEAN,                 -- delta_db > 3.0 AND pixel_count >= 5
    permit_count_nearby  INTEGER DEFAULT 0,       -- INE building permits within municipality
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
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

### 8.7 Gold Layer — UC-3: Land Development Opportunities

```sql
-- gold_analytics.development_sites — opportunity-scored development sites
-- Each site is a cluster of contiguous BUPI parcels in urban/urbanizable zones.
-- Contiguity algorithm: ST_ClusterDBSCAN(geom_pt, eps := 0, minpoints := 1)
-- Source: silver_geo.parcel_buildability grouped by ST_ClusterDBSCAN clusters
CREATE TABLE gold_analytics.development_sites (
    site_key             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geom                 GEOMETRY(MULTIPOLYGON, 3763), -- ST_Union of component parcels
    municipality         TEXT NOT NULL,
    parish               TEXT,
    dicofre              VARCHAR(6),
    total_area_m2        DOUBLE PRECISION,
    parcel_count         INTEGER,
    -- Zoning
    zone_category        TEXT,                    -- Solo Urbano / Solo Rústico (majority)
    land_classification  TEXT,
    -- Land use
    cos_level_1          TEXT,                    -- Dominant COS level 1
    is_vacant            BOOLEAN,
    is_agricultural      BOOLEAN,
    is_built             BOOLEAN,
    -- Building coverage
    has_building         BOOLEAN,
    building_coverage_pct NUMERIC(5,4),           -- Aggregate across site parcels
    -- Constraints
    srup_ran_flag        BOOLEAN DEFAULT FALSE,
    srup_ren_flag        BOOLEAN DEFAULT FALSE,
    srup_dph_flag        BOOLEAN DEFAULT FALSE,
    srup_ic_flag         BOOLEAN DEFAULT FALSE,
    -- ARU
    is_aru               BOOLEAN DEFAULT FALSE,
    -- Economics (dependency on UC-1 hedonic model)
    est_gba_m2           DOUBLE PRECISION,        -- Estimated gross building area
    local_eur_per_m2     NUMERIC(10,2),           -- From UC-1 hedonic model
    est_revenue          NUMERIC(14,2),
    est_cost             NUMERIC(14,2),
    est_margin           NUMERIC(14,2),
    -- Scoring
    opportunity_score    NUMERIC(5,2),            -- Composite score 0-100
    -- P2 enrichment
    sar_activity_flag    BOOLEAN,                 -- Sentinel-1 SAR (nullable until P2)
    _updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_dev_sites_geom ON gold_analytics.development_sites USING GIST(geom);
CREATE INDEX idx_dev_sites_municipality ON gold_analytics.development_sites(municipality);
CREATE INDEX idx_dev_sites_score ON gold_analytics.development_sites(opportunity_score DESC);

-- gold_analytics.site_parcels — BUPI parcels per development site
-- Links individual parcels to their parent development site.
-- NumeroMatriz + Dicofre → Caderneta Predial for ownership lookup.
CREATE TABLE gold_analytics.site_parcels (
    site_key             UUID REFERENCES gold_analytics.development_sites(site_key),
    process_id           INTEGER NOT NULL,
    matrix_number        TEXT,                    -- NumeroMatriz (ownership lookup key)
    dicofre              VARCHAR(6),
    area_m2              DOUBLE PRECISION,
    PRIMARY KEY (site_key, process_id)
);
```

### 8.8 Gold Reporting — Fact Tables & Materialized Views

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

LAYER 7 — UC-3 Land Opportunities (Sprint 9-11, post-MVP)

  Bronze (existing):
    raw_bupi + raw_cos2023 + raw_crus_ordenamento + raw_srup_ic/ran/dph + raw_cadastro
    ──► stg_bupi, stg_cos2023, stg_crus_ordenamento, stg_srup_*, stg_cadastro

  Bronze (new — P1):
    raw_building_footprints ──► stg_building_footprints

  Bronze (new — P2):
    raw_sar_change ──► stg_sar_change
    (SAR pipeline: Sentinel-1 GRD → rasterio/SNAP → zonal stats per BUPI parcel → PostGIS)

  Silver (existing, newly documented):
    stg_cos2023 ──► silver_geo.land_use
    stg_crus_ordenamento ──► silver_geo.zoning

  Silver (new — P1):
    stg_bupi ⊕ zoning ⊕ land_use ⊕ stg_srup_* ⊕ building_footprints
    ──► silver_geo.parcel_buildability
    (pre-filtered to CRUS municipality extents, materialized table)

  Silver (new — P2):
    stg_bupi ⊕ stg_sar_change ⊕ stg_building_permits
    ──► silver_geo.parcel_construction_activity

  Gold:
    parcel_buildability → ST_ClusterDBSCAN → site aggregation
    ⊕ parcel_construction_activity (P2)
    ──► gold_analytics.development_sites + site_parcels
```

### 10.2 Critical Path

```
S08 + S12 ──► dim_geography ──► S03 geocoding ──► unified_listings
  ──► neighbourhood_market_stats ──► hedonic_features
    ──► hedonic model ──► property_valuation
      ──► investment_opportunities (UC-1 MVP at Week 12)
        ──► UC-2 additions (Week 16)

UC-3 critical path (post-MVP, Weeks 17-22):
  S42 Building Footprints + existing bronze (BUPI/COS/CRUS/SRUP)
    ──► parcel_buildability ──► development_sites (UC-3 MVP at Week 19)
      ──► SAR + ARU + REN enrichment (Week 22)

Critical path to UC-1: 6 sprints (12 weeks)
Critical path to UC-2: 8 sprints (16 weeks)
Critical path to UC-3: 11 sprints (22 weeks) — requires UC-1 hedonic model
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
│   # UC-3 (Sprint 9+)
│   ├── bupi_ingestion.py                 # Sprint 9 — Monthly (exists)
│   ├── bupi_bronze_load.py               # Sprint 9 — Triggered (exists)
│   ├── cos_ingestion.py                  # Sprint 9 — Ad-hoc (exists)
│   ├── cos_bronze_load.py                # Sprint 9 — Triggered (exists)
│   ├── crus_ingestion.py                 # Sprint 9 — Ad-hoc (exists)
│   ├── crus_bronze_load.py               # Sprint 9 — Triggered (exists)
│   ├── srup_ingestion.py                 # Sprint 9 — Ad-hoc (exists)
│   ├── srup_bronze_load.py               # Sprint 9 — Triggered (exists)
│   ├── cadastro_ingestion.py             # Sprint 9 — Ad-hoc (exists)
│   ├── cadastro_bronze_load.py           # Sprint 9 — Triggered (exists)
│   ├── building_footprints_ingestion.py  # Sprint 9 — Annual (P1)
│   ├── building_footprints_bronze_load.py # Sprint 9 — Triggered (P1)
│   └── sar_ingestion.py                  # Sprint 10 — Monthly (P2)
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

## 12. Sprint Plan (10 Sprints / 22 Weeks)

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
| Metabase docker-compose + DB roles | — | 0.5 | Metabase running on :3000, connected to warehouse with read-only role | Pending |
| Streamlit base app + Dockerfile + streamlit-keplergl | — | 1 | Streamlit on :8501 with placeholder pages, Kepler.gl rendering test | Pending |

**Exit criteria:** All bronze tables populated; dim_geography live; Nominatim + OSRM responding; Metabase + Streamlit accessible.

### Sprint 2 — Core Market Data (Weeks 3-4)

| Task | Source | Days | Deliverable | Tables affected | Status |
|---|---|---|---|---|---|
| Idealista API integration | S03/S04 | 5 | Daily sale + rental ingestion → `bronze_listings.raw_idealista` | — | ✅ Done |
| Idealista bronze schema (source-oriented) | S03/S04 | 1 | Raw JSONL → PostGIS with JSONB/TEXT columns (no parsing at bronze) | — | ✅ Done |
| Idealista ingestion DAG refactor | S03/S04 | 1 | Config dataclass, tenacity retry, cleanup task, template alignment | — | ✅ Done |
| ECB Euribor | S17 | 1 | Monthly rate DAG → `bronze_macro.raw_ecb` (3 Euribor series via SDMX API) | — | ✅ Done |
| Banco de Portugal | S16 | 2 | Monthly macro data → `bronze_macro.raw_bpstat` (3 domains, 16 datasets via JSON-stat API) | — | ✅ Done |
| Eurostat HPI | S18 | 1 | Quarterly HPI → `bronze_macro.raw_eurostat` (38 EU countries, JSON-stat API) | — | ✅ Done |
| dbt restructure + Cosmos | — | 2 | Domain staging (`geo/`, `ine/`, `listings/`, `macro/`, `location/`), Cosmos DbtTaskGroup, silver skeletons | `staging_dbt.stg_*` (11 views), `silver_market.macro_timeseries` | ✅ Done |
| Geocoding pipeline | — | 2 | Reverse geocoding via Nominatim → `bronze_listings.reverse_geocoded` (1,334 coords, 100% postal code coverage). Address enrichment in `unified_listings` (58% → 93% street addresses) | `bronze_listings.reverse_geocoded`, `silver_properties.unified_listings` (address_clean, postal_code) | ✅ Done |
| `dim_time` seed | — | 0.5 | Date dimension 2000–2035 via dbt_utils.date_spine (13,149 rows). YYYYMMDD integer key, ISO day-of-week, INE quarter labels | `gold_analytics.dim_time` | ✅ Done |
| `dim_property_type` seed | — | 0.5 | 16-row static dimension: Idealista raw type/subtype → Portuguese labels (tipo, subtipo, type_group) | `gold_analytics.dim_property_type` | ✅ Done |

**Exit criteria:** Idealista flowing daily; macro indicators loaded; dbt Cosmos pipeline operational; geocoding working. Per-source Cosmos DAGs (`dbt_{source}_build`) wired to all 8 bronze DAGs.

### Sprint 3 — Silver Layer: Unification (Weeks 5-6)

| Task | Source | Days | Deliverable | Affected tables | Status |
|---|---|---|---|---|---|
| Listing normalization | S03/S04 | 2 | Parse TEXT → typed: price → NUMERIC, area → NUMERIC, typology "T3" → rooms SMALLINT, floor codes, condition/energy to Portuguese, JSONB feature extraction (construction year, orientation, heating, amenity flags). Human-readable property_type/subtype/type_group columns | `silver_properties.unified_listings` | ✅ Done |
| Address cleaning | — | 2 | Nominatim reverse geocoding enriches raw addresses: street name fallback when raw lacks prefix (Rua, Av., etc.), postal code always from Nominatim. 58% → 93% street addresses, 0% → 100% postal codes | `silver_properties.unified_listings` (address_clean, postal_code) | ✅ Done |
| Geocode join | — | 1 | Spatial join via `ST_Within(point, freguesia_geom)` → `dim_geography.geo_key` + freguesia/concelho/distrito codes | `silver_properties.unified_listings` (geo_key, freguesia_code) | ✅ Done |
| SCD Type 2 price tracking | — | 2 | Incremental merge preserves first_seen_date, initial_price_eur, _created_at. Tracks price_change_count, listing_age_days. Staleness-based is_active (3-day rule + post-hook UPDATE) | `silver_properties.unified_listings` | ✅ Done |
| Imovirtual scraper | S05 | 7 | Second listing portal live → `bronze_listings.raw_imovirtual` | — |
| Cross-portal dedup | — | 3 | Hash(address + area + typology) matching, fuzzy fallback | `silver_properties.unified_listings` (property_hash), `silver_properties.listing_matches` |
| IMI/IMT reference tables | S31 | 2 | IMT transfer tax brackets (16 rows: primary/secondary/rural/other urban, 2025) and IMI municipal property tax rates (278 municipalities, urban 0.30%–0.45%). VALUES-based SQL models in gold_analytics | `gold_analytics.ref_imt_brackets`, `gold_analytics.ref_imi_rates` | ✅ Done |
| Census demographics model | S12 | 2 | BGRI 203K subsections → 2,882 freguesias: population by age band, household size, dwelling vacancy/tenure (42% avg vacancy, 82% owner-occupied), plus INE building aging ratio and repair %. 135 BGRI codes unmatched to CAOP (boundary changes) | `silver_geo.census_demographics` | ✅ Done |

**Exit criteria:** `unified_listings` with ~100K+ deduped active listings; >95% geocoded; `census_demographics` populated.

### Sprint 4 — Location Scores & Market Stats (Weeks 7-8)

| Task | Source | Days | Deliverable | Affected tables | Status |
|---|---|---|---|---|---|
| Transport stops model | S10 | 1 | Map OSM fclass → stop_type (50K rows from point + polygon layers), spatial join → geo_key, source/source_id columns, reproject to 3763 | `silver_location.transport_stops` | ✅ Done |
| OSM POIs model | S09 | 1 | Group fclass → category (food, health, education, …), spatial join → geo_key (304K rows from point + polygon layers) | `silver_location.pois` | ✅ Done |
| Transport proximity scores | S10 | 2 | Nearest stop per mode via crow-flies `ST_Distance` (EPSG:3763), exponential decay scoring with variable decay per mode, LATERAL + KNN joins. Raw distances + scores stored | `gold_analytics.property_location_scores` (transport_score, nearest_metro_m, nearest_rail_m, nearest_bus_m, metro_score, rail_score, bus_score) | |
| POI density / walkability | S09 | 2 | Count amenities within 500m/1km per listing | `gold_analytics.property_location_scores` (walkability_score, restaurants_500m, supermarkets_1km) | |
| Drive-time via OSRM | S11 | 3 | Batch routing: listing → city center, airport, nearest hospital | `gold_analytics.property_location_scores` (drive_city_center_min, drive_airport_min) | |
| Composite location score | — | 1 | Weighted combination of transport + walkability + drive-time | `gold_analytics.property_location_scores` (overall_location_score) | |
| Neighbourhood market stats | S01/S03 | 3 | Per-freguesia: median €/m², listing count, inventory months, turnover | `gold_analytics.neighbourhood_market_stats` | |
| Inside Airbnb ingestion | S15 | 1 | STR listings for Lisbon + Porto → `bronze_listings.raw_airbnb` | — | |
| PDM Zoning (LX + Porto) | S19 | 3 | Municipal zoning polygons → spatial overlay with listings | `silver_geo.zoning` | |
| Image classification: Claude Vision labeling | S03/S04 | 2 | Airflow DAG + structured prompt → Claude Vision API labels ~100K listings (render detection, condition 4-level, finish quality 4-level + confidence scores) → `bronze_listings.image_classifications` | `bronze_listings.image_classifications` | |
| Image classification: human validation | S03/S04 | 0.5 | Sample 500 listings, verify Claude labels, measure agreement (target >90% per feature) | — | |
| Image classification: CNN distillation | — | 3 | Multi-task MobileNetV2 trained on Claude labels. 3 heads: render (binary), condition (4-class), finish (4-class). ONNX export. Targets: >95% render, >85% condition, >80% finish | MinIO `s3://models/listing_classifier/v1/model.onnx` | |
| Image classification: Airflow deployment | S03/S04 | 1 | ONNX Runtime in Airflow worker. `image_classification_dag` triggered after bronze load. dbt staging + 6 new columns in `unified_listings` | `silver_properties.unified_listings` (cv_is_render, cv_condition, cv_finish_quality + confidences) | |

**Exit criteria:** Every listing has location scores; neighbourhood stats computed; `transport_stops` and `pois` populated. Image classification pipeline operational with CNN inference on new listings.

### Sprint 5 — Hedonic Model & Valuation (Weeks 9-10)

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| Hedonic feature assembly | — | 3 | Join `unified_listings` + `property_location_scores` + `census_demographics` + `neighbourhood_market_stats` + `zoning` into feature vector | `gold_analytics.hedonic_features` |
| Hedonic model training | — | 5 | OLS/Ridge regression on log(price_sqm) ~ property + location + neighbourhood features | Model artifact (pickle/ONNX) |
| Model validation | — | 2 | Cross-validation: R² ≥ 0.73, MAPE < 18%; residual analysis by geography | Validation report |
| Property comparables | — | 3 | KNN on feature space: top-10 similar listings within 2km, same typology band | `gold_analytics.property_comparables` |
| Property valuation | — | 2 | Predicted €/m² + comp-weighted €/m² → blended fair value, gap %, signal (undervalued/fair/overpriced) | `gold_analytics.property_valuation` |
| Seed renovation cost table | — | 1 | Manual €/m² estimates by scope (cosmetic, light, full, structural) | `gold_analytics.ref_renovation_costs` |
| Seed area catalysts | — | 2 | Known infrastructure projects (metro extensions, hospitals, university campuses) with geo + timeline | `gold_analytics.ref_area_catalysts` |

**Exit criteria:** Every sale listing has predicted fair value and `valuation_signal` (undervalued / fair / overpriced).

### Sprint 6 — UC-1 MVP: Investment Opportunities (Weeks 11-12)

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| Investment yield analysis | S04/S15/S31 | 4 | LTR yield (€/m² rent ÷ price), STR yield (Airbnb RevPAR × occupancy), net of IMI/IMT/condominium | `gold_analytics.investment_yield_analysis` |
| Renovation opportunity | (ref table) | 3 | Match undervalued listings to reno cost estimates → post-reno value, ROI % | `gold_analytics.renovation_opportunity` |
| Neighbourhood trajectory | — | 3 | YoY price trend + population growth + vacancy change + catalyst proximity → trajectory score | `gold_analytics.neighbourhood_trajectory` |
| Investment opportunities view | — | 2 | Composite ranking: valuation gap × yield × trajectory × location → **UC-1 LIVE** | `gold_analytics.investment_opportunities` (materialized view) |
| Serving: Investment Dashboard (Metabase) | — | 3 | KPIs, ranked table, yield vs. price scatter, filters (budget, location, typology, min yield) | — |
| Serving: Investment Map (Kepler.gl) | — | 1 | Listing points colored by valuation gap, neighbourhood trajectory polygons, infrastructure catalysts | — |
| Serving: Property Valuator (Streamlit) | — | 1 | Enter address/listing URL → predicted value, valuation gap, comparable sales, neighbourhood stats | — |
| INE Rental Price Index | S29 | 0.5 | Official rent indices → `bronze_ine.raw_indicators` (already ingested, add to dbt) | `silver_market.macro_timeseries` (new indicator rows) |
| ARU boundaries | S20 | 2 | Urban Rehabilitation Areas → spatial overlay with listings | `silver_geo.zoning` (is_aru flag), `gold_analytics.hedonic_features` (is_aru) |

**🏁 MILESTONE 1 (Week 12): UC-1 MVP LIVE.** Investors can query ranked opportunities.

### Sprint 7 — Enhancements + UC-2 Foundation (Weeks 13-14)

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| Imovirtual rentals | S06 | 1 | Second rental source → `bronze_listings.raw_imovirtual` rentals | `silver_properties.unified_listings` (new rows) |
| RNAL scraping | S14 | 5 | AL license registry → `bronze_listings.raw_rnal` | — |
| STR registry (RNAL + Airbnb) | S14/S15 | 2 | Merge RNAL licenses + Airbnb listings → licensed vs unlicensed STR map | `silver_properties.str_registry`, `gold_analytics.investment_yield_analysis` (licensing risk) |
| School data (InfoEscolas) | S22 | 5 | Schools geocoded + exam scores → spatial join | `silver_location.schools`, `gold_analytics.property_location_scores` (education_score, schools_1km) |
| Healthcare facilities | S23 | 2 | Hospitals/clinics geocoded + type/operator | `silver_location.healthcare_facilities`, `gold_analytics.property_location_scores` (healthcare_score, nearest_hospital_m) |
| GTFS transport schedules | S24 | 3 | Route count + service frequency enrichment | `silver_location.transport_stops` (route_count, service_frequency), `gold_analytics.property_location_scores` (transport_score recalc) |
| pgRouting network distances | S11 | 2 | Load OSM road graph into PostGIS, build topology. Replace crow-flies with network walking distance for metro/bus/tram and driving distance for rail/airport | `gold_analytics.property_location_scores` (recalc with network distances) |
| OSRM time-based accessibility | S11 | 2 | Batch OSRM API calls: walking time to nearest metro/bus, driving time to airport/rail. Add travel-time columns and time-based cutoffs replacing hard radius | `gold_analytics.property_location_scores` (nearest_metro_walk_min, nearest_air_drive_min) |
| Recalibrate hedonic model v2 | — | 2 | Add education_score + healthcare_score + network-based transport scores to feature vector, retrain | `gold_analytics.hedonic_features`, `gold_analytics.property_valuation` (refreshed) |
| Refresh investment_opportunities | — | 1 | Recompute with improved location + valuation scores | `gold_analytics.investment_opportunities` (refreshed) |

**Exit criteria:** Location scores include education + healthcare; transport scores upgraded to network distances (pgRouting) and travel times (OSRM); STR intelligence live; hedonic model v2 deployed.

### Sprint 8 — UC-2 MVP + Production Hardening (Weeks 15-16)

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| Competitive developments | S34 | 5 | Competing new-build projects mapped + unit inventory | `silver_properties.competitive_developments` |
| Absorption rate model | — | 3 | Days-on-market by segment (type × location × price band) | `gold_analytics.absorption_rate_model` |
| Location price premiums | — | 2 | Extract hedonic coefficients as lookup: metro proximity → €/m² premium | `gold_analytics.location_price_premiums` |
| Unit premiums calibration | — | 2 | Floor/view/orientation → premium/discount lookup from hedonic residuals | `gold_analytics.ref_unit_premiums` |
| Development projects import | — | 2 | Developer project data entry (units, typologies, target prices) | `gold_analytics.development_projects` |
| Unit pricing recommendation | — | 3 | Per-unit: base €/m² × premiums × market position → recommended price, **UC-2 LIVE** | `gold_analytics.unit_pricing_recommendation` |
| Project pricing summary | — | 1 | Roll up unit recommendations → project GDV, margin, sell-through timeline | `gold_analytics.project_pricing_summary` |
| Serving: Pricing Dashboard (Metabase) | — | 3 | Unit pricing matrix, competition map (2km radius), absorption timeline, floor/view premium chart | — |
| Serving: Pricing Simulator (Streamlit) | — | 1 | Select development project → adjust unit attributes → see recommended price, margin, absorption forecast | — |
| CI data integration (if license) | S02 | 3 | Transaction prices → validate hedonic predictions, calibrate gap % | `silver_properties.unified_listings` (transaction_price), `gold_analytics.property_valuation` (recalibrated) |
| Data quality monitoring | — | 2 | dbt tests + source freshness alerts + row count anomaly detection | All models |
| Documentation | — | 2 | Data dictionary + user guide + lineage diagrams | — |
| Backup + recovery test | — | 1 | pg_dump restore verified, WAL archiving confirmed | — |

**🏁 MILESTONE 2 (Week 16): UC-2 MVP LIVE + Production Release.**

### Sprint 9 — UC-3: Land Development Opportunities (Weeks 17-19)

**Prerequisite:** UC-1 hedonic model must be complete before economics model task.

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| MS Building Footprints ingestion | S42 | 2 | ~5M polygons → MinIO → PostGIS | `bronze_geo.raw_building_footprints` |
| Building footprints staging + silver model | S42 | 2 | Cleaned footprints with EPSG:3763 | `stg_building_footprints`, `silver_geo.building_footprints` |
| Vacant land detection model | S39/S40 | 3 | COS non-artificial × CRUS urban zones → candidate sites | `silver_geo.parcel_buildability` (is_vacant, is_agricultural flags) |
| Constraint overlay | S41 | 2 | SRUP flags per parcel (RAN/REN/DPH/IC) | `silver_geo.parcel_buildability` (srup_*_flag columns) |
| Parcel assembly (ST_ClusterDBSCAN) | S38 | 4 | Contiguous BUPI parcels grouped into development sites | `gold_analytics.development_sites`, `gold_analytics.site_parcels` |
| Development economics model | UC-1 | 3 | GBA estimate × local €/m² → revenue, cost, margin | `gold_analytics.development_sites` (est_* columns) |
| Opportunity scoring + materialized table | — | 2 | Composite opportunity_score per site | `gold_analytics.development_sites` (opportunity_score) |
| Serving: Land Dashboard (Metabase) | — | 2 | Map of development sites (choropleth by opportunity_score), ranked table, zoning filter, constraint toggles | — |
| Serving: Parcel Explorer (Kepler.gl) | — | 2 | BUPI parcels colored by buildability, SRUP constraints (toggle), COS land use (toggle), building footprints (toggle) | — |
| Serving: Site Analyzer (Streamlit) | — | 1 | Click on map → assemblable parcels, zoning params, constraints, ownership keys, estimated GBA + return | — |
| **Total** | | **23** | (15 working days × 1.5 engineers = 22.5 available) | |

**🏁 MILESTONE 3 (Week 19): UC-3 MVP LIVE.**

### Sprint 10 — UC-3 Enhancements (Weeks 20-22)

| Task | Source | Days | Deliverable | Affected tables |
|---|---|---|---|---|
| Sentinel-1 SAR pipeline | S43 | 9 | Change detection → construction activity flags per parcel | `bronze_geo.raw_sar_change`, `stg_sar_change`, `silver_geo.parcel_construction_activity` |
| ARU boundaries ingestion | S20 | 2 | ARU overlay → is_aru flag on development sites | `silver_geo.parcel_buildability` (is_aru), `gold_analytics.development_sites` |
| INE Building Permits | S21 | 2 | Permit data → active construction validation | `bronze_ine.raw_building_permits`, `stg_building_permits` |
| REN ingestion (SRUP Phase 2) | S41 | 3 | Ecological reserve → ren_flag on sites | `bronze_regulatory.raw_srup_ren`, `stg_srup_ren` |
| UC-3 model recalibration | — | 2 | Incorporate SAR + ARU + REN + permits into opportunity_score | `gold_analytics.development_sites` (recalibrated) |
| **Total** | | **18** | (15 working days × 1.5 engineers = 22.5 available) | |

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
| Volume | `bronze_regulatory.raw_bupi` | ≥ 3M rows after load | Critical |
| Not null | `parcel_buildability.process_id` | 0% null | Critical |
| Not null | `parcel_buildability.dicofre` | 0% null | Critical |
| Range | `parcel_buildability.building_coverage_pct` | 0.0 to 1.0 | Warning |
| Range | `development_sites.opportunity_score` | 0 to 100 | Warning |
| Referential | `site_parcels.site_key` | All FK valid → development_sites | Critical |
| Accepted values | `parcel_buildability.zone_category` | Solo Urbano, Solo Rústico, NULL | Warning |

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
| R9 | CRUS coverage limited to 5 municipalities | High | High | Expand CRUS WFS queries to more municipalities; use COS as fallback for zoning |
| R10 | Sentinel-1 SAR processing complexity + skills gap | Med | Med | Start with building footprints (P1); SAR is enrichment (P2), not blocking. May need remote sensing contractor. |
| R11 | BUPI parcel boundaries are declaration-based (not surveyed) | Med | Low | Acceptable for analytical screening; formal cadastre (S44) validates specific sites |
| R12 | Spatial join performance at scale (3.25M × 784K × 5M) | Med | High | Pre-filter BUPI to CRUS municipality extents (~500K parcels); materialize intermediate tables; partition by municipality |
| R13 | Building footprint false positives/negatives (ML quality) | Med | Med | Acceptable for screening; flag low-confidence matches; specific sites verified via aerial imagery |
| R14 | COS 2023 temporal lag (2-3 years old) | Med | Med | Land classified as vacant in 2023 may already be developed. SAR (P2) partially mitigates; building footprints (P1) provide more recent signal |
| R15 | UC-3 economics model depends on UC-1 hedonic model | High | High | Sprint 9 economics task blocked until UC-1 complete. Fallback: use INE average €/m² by municipality |

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
| 9 | 17-19 | 20 | UC-3 MVP: building footprints, parcel buildability, opportunity scoring | 🏁 **UC-3 MVP** |
| 10 | 20-22 | 18 | UC-3 enhancements: SAR, ARU, REN, building permits | UC-3 v2 |
| **Total** | **22** | **186** | | **All three use cases live** |

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
| BUPI cadastral parcels (S38) | ~3.25M polygons | 2 GB | Monthly |
| COS 2023 land use (S39) | ~784K polygons | 500 MB | ~5 years |
| CRUS zoning (S40) | ~5K zones (5 municipalities) | 100 MB | Ad-hoc |
| SRUP constraints (S41) | ~4K features (IC+RAN+DPH) | 400 MB | Ad-hoc |
| Cadastro Predial (S44) | partial coverage | 300 MB | Ad-hoc |
| MS Building Footprints (S42) | ~5M polygons | 1.5-2 GB | Annual |
| Sentinel-1 SAR processed (S43) | per-parcel flags | 50 MB | Monthly |

**Total estimated: ~28 GB in PostgreSQL + ~35 GB in MinIO**

---

## 16. Future Expansion (P3/P4 Roadmap)

Once MVP is stable (Week 16+), layer in deferred sources:

### Phase 2A — Risk & Environment (Weeks 17-20)

| Source | Value Add | Expected Improvement |
|---|---|---|
| S35 APA Flood Risk | flood_risk_level in hedonic model | +1-2% R² in flood zones |
| S27 Noise Maps (LX/Porto) | noise_level_db in hedonic + pricing | +2-3% R²; noise_discount in UC-2 |
| S13 ADENE Certificates (if FOI) | kWh/m², CO2, detailed energy | Better energy premium |

### Phase 2D — Land Development Intelligence (Weeks 17-22, UC-3)

| Source | Value Add |
|---|---|
| S42 MS Building Footprints | Vacant plot detection, building coverage per parcel |
| S43 Sentinel-1 SAR | Active construction detection (cloud-independent) |
| S20 ARU Boundaries | Tax benefit flagging for rehabilitation zones |
| S21 INE Building Permits | Authorized construction validation |
| SRUP REN (Phase 2) | Ecological reserve constraint (critical for buildability) |

### Phase 2B — Supply Pipeline & Costs (Weeks 23-26)

| Source | Value Add |
|---|---|
| S25 IMPIC Construction Costs | Calibrate renovation cost model with real indices |
| S28 PVGIS Solar | Precise sun exposure for orientation premiums |

### Phase 2C — Coverage & Niche (Weeks 27+)

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

## 17. Serving Layer

### 17.1 Overview

| Component | Purpose | Users | Technology |
|-----------|---------|-------|------------|
| **Metabase** | BI dashboards — KPIs, ranked tables, filters, charts (non-map analytics) | Business users, investors, developers | Metabase OSS 0.48+ (Docker) |
| **Kepler.gl** | Rich geospatial visualization for all use cases — polygon rendering, multi-layer overlays, heatmaps | All users (spatial exploration) | Kepler.gl 3.0 embedded in Streamlit via `streamlit-keplergl` |
| **Streamlit** | Host for Kepler maps + custom interactive tools — site analyzer, valuator, pricing simulator | All users (task-specific workflows) | Streamlit 1.30+ (Docker) |

**API serving deferred.** PostgREST/FastAPI not needed for MVP — users interact via Metabase dashboards and Streamlit/Kepler apps. Add API layer later if external integrations are needed.

**Why Kepler.gl for all use cases:** All three use cases are fundamentally spatial — listings (UC-1), developments (UC-2), and parcels (UC-3) are all geolocated. Kepler.gl handles points, polygons, heatmaps, and multi-layer toggling natively with GPU-accelerated rendering for millions of features. Metabase handles the non-spatial analytics (tables, charts, KPIs, filters).

### 17.2 Docker Compose Services

```yaml
# Metabase — BI Dashboards (KPIs, tables, charts, filters)
metabase:
  image: metabase/metabase:v0.48.0
  ports:
    - "3000:3000"
  environment:
    MB_DB_TYPE: postgres
    MB_DB_DBNAME: metabase
    MB_DB_PORT: 5432
    MB_DB_USER: metabase
    MB_DB_PASS: ${METABASE_DB_PASSWORD}
    MB_DB_HOST: warehouse
  depends_on:
    - warehouse

# Streamlit + Kepler.gl — Maps & Custom Apps
# Kepler.gl embedded via streamlit-keplergl package (no separate container)
streamlit:
  build:
    context: ./apps
    dockerfile: Dockerfile
  ports:
    - "8501:8501"
  environment:
    DATABASE_URL: postgres://streamlit:${STREAMLIT_DB_PASSWORD}@warehouse:5432/warehouse
  depends_on:
    - warehouse
```

**Two containers only.** Kepler.gl runs embedded inside Streamlit via the `streamlit-keplergl` Python package — no separate service needed.

### 17.3 PostgreSQL Roles for Serving

```sql
-- Metabase read-only role (dashboards, KPIs, charts)
CREATE ROLE metabase LOGIN PASSWORD '${METABASE_DB_PASSWORD}';
GRANT USAGE ON SCHEMA gold_analytics, silver_geo, silver_properties, silver_market TO metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA gold_analytics TO metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_geo TO metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_properties TO metabase;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_market TO metabase;

-- Streamlit + Kepler.gl read-only role (maps, custom apps)
CREATE ROLE streamlit LOGIN PASSWORD '${STREAMLIT_DB_PASSWORD}';
GRANT USAGE ON SCHEMA gold_analytics, silver_geo, silver_properties TO streamlit;
GRANT SELECT ON ALL TABLES IN SCHEMA gold_analytics TO streamlit;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_geo TO streamlit;
GRANT SELECT ON ALL TABLES IN SCHEMA silver_properties TO streamlit;
```

### 17.4 Dashboard & App Inventory

**Metabase Dashboards:**

| Dashboard | Use Case | Key Visualizations | Sprint |
|-----------|----------|-------------------|--------|
| Investment Board | UC-1 | Map of opportunities, ranked table by investment_score, yield vs. price scatter, filters (budget, location, typology, min yield) | Sprint 6 |
| Pricing Board | UC-2 | Unit pricing matrix, competition map (2km radius), absorption timeline, floor/view premium chart | Sprint 8 |
| Land Opportunities | UC-3 | Map of development sites (choropleth by opportunity_score), ranked table, zoning filter, constraint toggles (RAN/DPH/IC), parcel drill-down | Sprint 9 |

**Kepler.gl Maps (embedded in Streamlit):**

| Map | Use Case | Layers | Sprint |
|-----|----------|--------|--------|
| Investment Map | UC-1 | Listing points colored by valuation gap, neighbourhood trajectory polygons, infrastructure catalysts | Sprint 6 |
| Parcel Explorer | UC-3 | BUPI parcels colored by buildability, SRUP constraint polygons (toggle), COS land use (toggle), building footprints (toggle), CRUS zoning boundaries | Sprint 9 |
| Opportunity Heatmap | UC-3 | Hexbin aggregation of opportunity_score, development site polygons, ARU overlay | Sprint 9 |

**Streamlit Apps:**

| App | Use Case | Features | Sprint |
|-----|----------|----------|--------|
| Property Valuator | UC-1 | Enter address/listing URL → predicted value, valuation gap, comparable sales, neighbourhood stats | Sprint 6 |
| Pricing Simulator | UC-2 | Select development project → adjust unit attributes → see recommended price, margin, absorption forecast | Sprint 8 |
| Site Analyzer | UC-3 | Click on map → show assemblable parcels, zoning params, constraints, ownership keys (NumeroMatriz), estimated GBA + return | Sprint 9 |

### 17.5 Serving Layer Architecture Diagram

```
                    ┌──────────────────────────────────────────┐
                    │              END USERS                     │
                    │                                            │
                    │  Investors   Developers   Analysts   GIS  │
                    └──────┬─────────┬──────────┬─────────┬────┘
                           │         │          │         │
                    ┌──────▼──┐  ┌───▼────────┐           │
                    │Metabase │  │ Streamlit   │           │
                    │ :3000   │  │  :8501      │           │
                    │         │  │             │           │
                    │Dashboard│  │ Custom Apps │           │
                    │  KPIs   │  │ ┌─────────┐│           │
                    │ Tables  │  │ │Kepler.gl││           │
                    │ Filters │  │ │(embedded)││           │
                    │ Charts  │  │ │ Maps     ││           │
                    │         │  │ └─────────┘│           │
                    └────┬────┘  └─────┬──────┘           │
                         │             │                   │
                         └──────┬──────┘                   │
                                │                          │
                         ┌──────▼──────┐                   │
                         │  PostgreSQL  │◄─────────────────┘
                         │  (warehouse) │   QGIS direct
                         │              │   connection
                         │ gold_analytics│
                         │ silver_geo    │
                         │ silver_*      │
                         └──────────────┘
```

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
| Investment Map (Kepler.gl) | Listing points rendered with valuation gap coloring | Yes |
| Property Valuator (Streamlit) | Address lookup returns predicted value + comps | No |

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
| Metabase Pricing Dashboard | Accessible with unit matrix + competition map | Yes |
| Pricing Simulator (Streamlit) | Unit attribute adjustment returns recommended price | No |

### Milestone 3: UC-3 MVP (Week 19)

| Criteria | Target | Hard Fail? |
|---|---|---|
| BUPI parcels loaded | ≥ 3M parcels | Yes |
| CRUS zoning loaded | ≥ 5 municipalities | Yes |
| Building footprints loaded | ≥ 4M footprints for Portugal | Yes |
| Opportunity sites identified | Sites in ≥ 4 of 5 CRUS municipalities | Yes |
| Spatial join coverage | 100% of BUPI parcels within CRUS extents processed | Yes |
| parcel_buildability materialization | Refreshes in < 30 minutes | No |
| Metabase Land Dashboard | Accessible with working filters | Yes |
| Parcel Explorer (Kepler.gl) | BUPI parcels rendered with buildability coloring + constraint toggles | Yes |
| Site Analyzer (Streamlit) | Click-to-analyze workflow returns parcel assembly + zoning + economics | No |

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
