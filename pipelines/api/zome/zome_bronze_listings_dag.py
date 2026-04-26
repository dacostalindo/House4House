"""Zome PT bronze loading DAG — load listings from MinIO to PostGIS.

To trigger: Airflow UI → zome_bronze_load_listings → Trigger DAG
"""

from pipelines.api.zome.zome_config import ZOME_BRONZE_LISTINGS_CONFIG
from pipelines.scraping.template.scraping_bronze_template import create_bronze_loading_dag

dag = create_bronze_loading_dag(ZOME_BRONZE_LISTINGS_CONFIG)
