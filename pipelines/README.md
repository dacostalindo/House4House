# Pipelines

Ingestion pipelines for the Portugal Real Estate Data Warehouse.
Scope: raw source → MinIO landing zone. Bronze table loading is a separate step, done only after the raw data has been explored and the schema confirmed.

---

## Architecture

All pipelines follow the **Medallion pattern** defined in the project plan:

```
External Source
      ↓
  [ Ingestion ]  ← this directory
      ↓
  MinIO (raw)    s3://raw/{source}/{version}/{filename}
      ↓
  Bronze (PostGIS)   — not covered here
      ↓
  Silver (dbt)
      ↓
  Gold (dbt)
```

---

## Flow Types

The project defines four ingestion patterns. Each has its own template.

| Flow | Pattern | Sources | Template |
|------|---------|---------|----------|
| A | REST API | INE, BPStat, Eurostat, ECB, Idealista | `api/template/` — _planned_ |
| B | Web scraping | Imovirtual, RNAL, InfoEscolas, Competitive Devs | `scraper/template/` — _planned_ |
| C | GIS file download | CAOP, OSM, PDM, ARU | `gis/template/` — **available** |
| D | Derived computation | Location scores, valuations | dbt-only, no ingestion DAG |

---

## Directory Structure

```
pipelines/
├── gis/                        Flow C — GIS file sources
│   ├── template/               Reusable DAG factory for all GIS sources
│   ├── caop/                   S08 — CAOP Boundaries (DGT)
│   ├── osm/                    S09/S10/S11 — OpenStreetMap  (planned)
│   ├── pdm/                    S19 — PDM Zoning             (planned)
│   └── aru/                    S20 — ARU Boundaries         (planned)
│
├── api/                        Flow A — REST API sources    (planned)
│   ├── template/
│   ├── ine/                    S01/S12/S29 — INE APIs
│   ├── bpstat/                 S16 — Banco de Portugal
│   ├── ecb/                    S17 — ECB Euribor
│   ├── eurostat/               S18 — Eurostat HPI
│   └── idealista/              S03/S04 — Idealista listings
│
└── scraper/                    Flow B — Web scraping        (planned)
    ├── template/
    ├── imovirtual/             S05/S06 — Imovirtual listings
    ├── rnal/                   S14 — AL Licenses
    ├── infoescolas/            S22 — School quality
    └── comp_devs/              S34 — Competitive developments
```

---

## Airflow Variables Required

All pipelines read credentials from Airflow Variables (never hardcoded).
Set these before running any DAG:

```bash
airflow variables set MINIO_ENDPOINT   localhost:9000
airflow variables set MINIO_ACCESS_KEY <key>
airflow variables set MINIO_SECRET_KEY <secret>
```

Flow A pipelines add source-specific variables (API keys, etc.) — documented in each source's own directory.

---

## Adding a New Pipeline

1. Pick the matching template (`gis/`, `api/`, or `scraper/`)
2. Create `pipelines/{flow}/{source}/` with:
   - `{source}_config.py` — instantiate the config dataclass
   - `{source}_ingestion_dag.py` — one-liner: `dag = create_*_dag(CONFIG)`
3. Airflow auto-discovers the DAG file on next scheduler cycle
