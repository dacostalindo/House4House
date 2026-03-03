"""
INE API Ingestion DAG — Housing + Demographics indicators

Instantiated from the API ingestion template using INE-specific config.
All pipeline logic lives in the template; all INE specifics live in ine_config.py.

To trigger: Airflow UI → ine_api_ingestion → Trigger DAG
No config parameters needed.
"""

from pipelines.api.ine.ine_config import INE_CONFIG
from pipelines.api.template.api_ingestion_template import create_api_ingestion_dag

dag = create_api_ingestion_dag(INE_CONFIG)
