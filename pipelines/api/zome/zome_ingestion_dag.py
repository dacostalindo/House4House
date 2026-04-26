"""Zome PT API ingestion DAG — fetch developments + listings from Supabase to MinIO.

To trigger: Airflow UI → zome_api_ingestion → Trigger DAG
"""

from pipelines.api.zome.zome_config import ZOME_CONFIG
from pipelines.api.template.api_ingestion_template import create_api_ingestion_dag

dag = create_api_ingestion_dag(ZOME_CONFIG)
