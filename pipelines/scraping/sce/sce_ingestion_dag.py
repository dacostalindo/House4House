"""SCE PCE ingestion DAG — scrape pre-energy certificates from sce.pt to MinIO.

To trigger: Airflow UI → sce_ingestion → Trigger DAG
"""

from pipelines.scraping.sce.sce_config import SCE_CONFIG
from pipelines.scraping.template.scraping_ingestion_template import create_scraping_ingestion_dag

dag = create_scraping_ingestion_dag(SCE_CONFIG)
