"""
BUPI Ingestion DAG — Simplified Cadastral Property Parcels (dados.gov.pt)

Instantiated from the GIS ingestion template using BUPI-specific config.
All pipeline logic lives in the template; all BUPI specifics live in bupi_config.py.

To trigger: Airflow UI → bupi_ingestion → Trigger DAG w/ config:
    {"version": "2026-03"}
"""

from pipelines.gis.bupi.bupi_config import BUPI_CONFIG
from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag

dag = create_gis_ingestion_dag(BUPI_CONFIG)
