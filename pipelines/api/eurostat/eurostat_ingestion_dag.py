"""Eurostat HPI Ingestion DAG — S18

Instantiated from the API ingestion template using Eurostat-specific config.
All pipeline logic lives in the template; all Eurostat specifics live in eurostat_config.py.

To trigger: Airflow UI → eurostat_api_ingestion → Trigger DAG
No config parameters needed.
"""

from pipelines.api.eurostat.eurostat_config import EUROSTAT_CONFIG
from pipelines.api.template.api_ingestion_template import create_api_ingestion_dag

dag = create_api_ingestion_dag(EUROSTAT_CONFIG)
