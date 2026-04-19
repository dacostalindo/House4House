"""RE/MAX PT bronze loading DAG — load development JSONL from MinIO to PostGIS.

To trigger: Airflow UI → remax_bronze_load → Trigger DAG
"""

from pipelines.scraping.remax.remax_config import REMAX_BRONZE_CONFIG
from pipelines.scraping.template.scraping_bronze_template import create_bronze_loading_dag

dag = create_bronze_loading_dag(REMAX_BRONZE_CONFIG)
