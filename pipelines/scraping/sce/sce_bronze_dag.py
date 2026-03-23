"""SCE PCE bronze loading DAG — load JSONL from MinIO into PostGIS bronze table.

To trigger: Airflow UI → sce_bronze_load → Trigger DAG
"""

from pipelines.scraping.sce.sce_config import SCE_BRONZE_CONFIG
from pipelines.scraping.template.scraping_bronze_template import create_bronze_loading_dag

dag = create_bronze_loading_dag(SCE_BRONZE_CONFIG)
