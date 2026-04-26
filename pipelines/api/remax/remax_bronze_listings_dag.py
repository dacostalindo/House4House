"""RE/MAX PT bronze loading DAG — load unit listings from MinIO to PostGIS.

To trigger: Airflow UI → remax_bronze_load_listings → Trigger DAG
"""

from pipelines.api.remax.remax_config import REMAX_BRONZE_LISTINGS_CONFIG
from pipelines.scraping.template.scraping_bronze_template import create_bronze_loading_dag

dag = create_bronze_loading_dag(REMAX_BRONZE_LISTINGS_CONFIG)
