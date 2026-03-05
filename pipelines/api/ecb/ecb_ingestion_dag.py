"""ECB Euribor Ingestion DAG — S17

Instantiated from the API ingestion template using ECB-specific config.
All pipeline logic lives in the template; all ECB specifics live in ecb_config.py.

To trigger: Airflow UI → ecb_api_ingestion → Trigger DAG
No config parameters needed.
"""

from pipelines.api.ecb.ecb_config import ECB_CONFIG
from pipelines.api.template.api_ingestion_template import create_api_ingestion_dag

dag = create_api_ingestion_dag(ECB_CONFIG)
