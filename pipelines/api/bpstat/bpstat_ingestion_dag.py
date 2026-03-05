"""BPStat Ingestion DAG — S16

Instantiated from the API ingestion template using BPStat-specific config.
All pipeline logic lives in the template; all BPStat specifics live in bpstat_config.py.

To trigger: Airflow UI → bpstat_api_ingestion → Trigger DAG
No config parameters needed.
"""

from pipelines.api.bpstat.bpstat_config import BPSTAT_CONFIG
from pipelines.api.template.api_ingestion_template import create_api_ingestion_dag

dag = create_api_ingestion_dag(BPSTAT_CONFIG)
