"""
COS 2023 Ingestion DAG — Land Use/Cover Map (DGT)

Instantiated from the GIS ingestion template using COS-specific config.
All pipeline logic lives in the template; all COS specifics live in cos_config.py.

To trigger: Airflow UI → cos2023_ingestion → Trigger DAG w/ config:
    {"version": "2023"}
"""

from pipelines.gis.cos.cos_config import COS_CONFIG
from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag

dag = create_gis_ingestion_dag(COS_CONFIG)
