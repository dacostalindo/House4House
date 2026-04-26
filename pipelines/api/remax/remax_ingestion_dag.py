"""RE/MAX PT development ingestion DAG — two-pass API scrape to MinIO.

To trigger: Airflow UI → remax_ingestion → Trigger DAG
"""

from pipelines.api.remax.remax_config import REMAX_CONFIG
from pipelines.scraping.template.scraping_ingestion_template import create_scraping_ingestion_dag

dag = create_scraping_ingestion_dag(REMAX_CONFIG)
