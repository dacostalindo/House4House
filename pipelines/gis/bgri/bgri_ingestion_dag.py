"""
BGRI Census 2021 DAG — S12 (INE)

Instantiated from the GIS ingestion template using BGRI-specific config.
All pipeline logic lives in the template; all BGRI specifics live in bgri_config.py.

To trigger: Airflow UI → s12_bgri_ingestion → Trigger DAG
No config parameters needed — URL and version are hardcoded (static source).
"""

from pipelines.gis.bgri.bgri_config import BGRI_CONFIG
from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag

dag = create_gis_ingestion_dag(BGRI_CONFIG)
