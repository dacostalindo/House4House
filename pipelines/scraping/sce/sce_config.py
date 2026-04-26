"""
SCE (Sistema de Certificação Energética) — Scraping Configuration

Source:  https://www.sce.pt/pesquisa-certificados/
Format:  HTML (server-rendered, Cloudflare Turnstile protected)
Method:  nodriver (undetected Chrome) → BeautifulSoup
Refresh: Weekly (pre-certificates update as new buildings are registered)

--- HOW TO TRIGGER ---

Trigger manually from Airflow UI:
    Airflow UI → sce_ingestion → Trigger DAG

--- REGIONS ---

3 distritos (Aveiro, Coimbra, Leiria) — initial scope matching core coverage area.
Each distrito is scraped as a separate Airflow task, iterating all concelhos within.
Expand to all 22 distritos when ready for full country coverage.
"""

from __future__ import annotations

from datetime import date

from pipelines.scraping.template.scraping_ingestion_template import (
    ScrapingRegion,
    ScrapingIngestionConfig,
)
from pipelines.scraping.template.scraping_bronze_template import BronzeTableConfig
from pipelines.scraping.sce.sce_scraper import sce_scrape_fn


# ---------------------------------------------------------------------------
# Regions (3 distritos — core coverage area)
# Concelhos are fetched dynamically from the SCE dropdown at scrape time.
# To expand to full country, uncomment the remaining distritos below.
# ---------------------------------------------------------------------------

SCE_REGIONS = [
    ScrapingRegion(code="01", name="AVEIRO", params={"distrito": "1"}),
    ScrapingRegion(code="06", name="COIMBRA", params={"distrito": "6"}),
    ScrapingRegion(code="10", name="LEIRIA", params={"distrito": "10"}),
    # --- Uncomment below for full country coverage (22 distritos) ---
    # ScrapingRegion(code="02", name="BEJA", params={"distrito": "2"}),
    # ScrapingRegion(code="03", name="BRAGA", params={"distrito": "3"}),
    # ScrapingRegion(code="04", name="BRAGANCA", params={"distrito": "4"}),
    # ScrapingRegion(code="05", name="C BRANCO", params={"distrito": "5"}),
    # ScrapingRegion(code="07", name="EVORA", params={"distrito": "7"}),
    # ScrapingRegion(code="08", name="FARO", params={"distrito": "8"}),
    # ScrapingRegion(code="09", name="GUARDA", params={"distrito": "9"}),
    # ScrapingRegion(code="11", name="LISBOA", params={"distrito": "11"}),
    # ScrapingRegion(code="12", name="PORTALEGRE", params={"distrito": "12"}),
    # ScrapingRegion(code="13", name="PORTO", params={"distrito": "13"}),
    # ScrapingRegion(code="14", name="SANTAREM", params={"distrito": "14"}),
    # ScrapingRegion(code="15", name="SETUBAL", params={"distrito": "15"}),
    # ScrapingRegion(code="16", name="VIANA DO CASTELO", params={"distrito": "16"}),
    # ScrapingRegion(code="17", name="VILA REAL", params={"distrito": "17"}),
    # ScrapingRegion(code="18", name="VISEU", params={"distrito": "18"}),
    # ScrapingRegion(code="19", name="ANGRA DO HEROISMO", params={"distrito": "19"}),
    # ScrapingRegion(code="20", name="HORTA", params={"distrito": "20"}),
    # ScrapingRegion(code="21", name="PONTA DELGADA", params={"distrito": "21"}),
    # ScrapingRegion(code="22", name="FUNCHAL", params={"distrito": "22"}),
]

# ---------------------------------------------------------------------------
# Ingestion config
# ---------------------------------------------------------------------------

SCE_CONFIG = ScrapingIngestionConfig(
    dag_id="sce_ingestion",
    source_name="sce",
    description=(
        "Scrape PCE (pre-energy certificates) from the SCE portal. "
        "3 distritos (Aveiro, Coimbra, Leiria) × all concelhos × all freguesias."
    ),
    target_url="https://www.sce.pt/wp-content/plugins/sce-pesquisa-certificados/functions.php",
    landing_url="https://www.sce.pt/pesquisa-certificados/",
    regions=SCE_REGIONS,
    scrape_fn=sce_scrape_fn,
    backend="nodriver",
    headless=False,
    browser_executable_path="/usr/bin/chromium",
    turnstile_wait_seconds=15,
    browser_restart_interval=500,
    request_delay=4.0,
    minio_prefix="sce_pce",
    trigger_dag_id="sce_bronze_load",
    tags=["sce", "energy-certificates", "pce"],
)

# ---------------------------------------------------------------------------
# Bronze config
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS bronze_regulatory.raw_sce_pce (
        id                 BIGSERIAL PRIMARY KEY,
        doc_number         VARCHAR(50) NOT NULL,
        morada             TEXT,
        fracao             VARCHAR(50),
        localidade         VARCHAR(200),
        concelho           VARCHAR(100),
        estado             VARCHAR(50),
        doc_substituto     VARCHAR(50),
        tipo_documento     VARCHAR(50),
        classe_energetica  VARCHAR(10),
        data_emissao       VARCHAR(20),
        data_validade      VARCHAR(20),
        freguesia_detail   VARCHAR(200),
        perito_num         VARCHAR(50),
        conservatoria      VARCHAR(200),
        sob_o_num          VARCHAR(50),
        artigo_matricial   VARCHAR(100),
        fracao_autonoma    VARCHAR(50),
        query_distrito     VARCHAR(10),
        query_concelho     VARCHAR(10),
        query_freguesia    VARCHAR(10),
        _scrape_date       DATE NOT NULL,
        _batch_id          VARCHAR(50),
        _ingested_at       TIMESTAMPTZ DEFAULT NOW(),
        _source            VARCHAR(50) DEFAULT 'sce_portal',
        _minio_path        TEXT,
        UNIQUE (doc_number, _batch_id)
    )
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_sce_pce_doc ON bronze_regulatory.raw_sce_pce(doc_number)",
    "CREATE INDEX IF NOT EXISTS idx_sce_pce_concelho_classe ON bronze_regulatory.raw_sce_pce(concelho, classe_energetica)",
    "CREATE INDEX IF NOT EXISTS idx_sce_pce_scrape_date ON bronze_regulatory.raw_sce_pce(_scrape_date)",
]

INSERT_SQL = """
    INSERT INTO bronze_regulatory.raw_sce_pce (
        doc_number, morada, fracao, localidade, concelho, estado,
        doc_substituto, tipo_documento, classe_energetica,
        data_emissao, data_validade, freguesia_detail, perito_num,
        conservatoria, sob_o_num, artigo_matricial, fracao_autonoma,
        query_distrito, query_concelho, query_freguesia,
        _scrape_date, _batch_id, _minio_path
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s
    )
"""


def _extract_scrape_date(object_name: str) -> str:
    """Extract scrape date from MinIO path: sce_pce/{region}/{YYYYMMDD}/{timestamp}.jsonl"""
    import re
    match = re.search(r"/(\d{8})/", object_name)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return date.today().isoformat()


def _flatten_sce_records(raw_records: list[dict], batch_id: str, minio_path: str) -> list[tuple]:
    """Convert JSONL records to INSERT tuples."""
    scrape_date = _extract_scrape_date(minio_path)
    rows = []
    for r in raw_records:
        rows.append((
            r.get("doc_number", ""),
            r.get("morada", ""),
            r.get("fracao", ""),
            r.get("localidade", ""),
            r.get("concelho", ""),
            r.get("estado", ""),
            r.get("doc_substituto", ""),
            r.get("tipo_documento", ""),
            r.get("classe_energetica", ""),
            r.get("data_emissao", ""),
            r.get("data_validade", ""),
            r.get("freguesia_detail", ""),
            r.get("perito_num", ""),
            r.get("conservatoria", ""),
            r.get("sob_o_num", ""),
            r.get("artigo_matricial", ""),
            r.get("fracao_autonoma", ""),
            r.get("query_distrito", ""),
            r.get("query_concelho", ""),
            r.get("query_freguesia", ""),
            scrape_date,
            batch_id,
            minio_path,
        ))
    return rows


SCE_BRONZE_CONFIG = BronzeTableConfig(
    dag_id="sce_bronze_load",
    source_name="sce",
    description="Load SCE PCE JSONL from MinIO into PostGIS bronze table",
    schema_name="bronze_regulatory",
    table_name="raw_sce_pce",
    create_table_sql=CREATE_TABLE_SQL,
    create_indexes_sql=CREATE_INDEXES_SQL,
    insert_sql=INSERT_SQL,
    minio_bucket="raw",
    minio_prefix="sce_pce",
    flatten_fn=_flatten_sce_records,
    file_format="jsonl",
    delete_before_insert=False,
    trigger_dag_id="dbt_sce_build",
    tags=["sce", "bronze", "energy-certificates"],
)
