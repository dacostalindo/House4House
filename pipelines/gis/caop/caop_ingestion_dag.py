"""
CAOP Ingestion DAG — S08 CAOP Boundaries (DGT)

Instantiated from the GIS ingestion template using CAOP-specific config.
All pipeline logic lives in the template; all CAOP specifics live in caop_config.py.

To trigger: Airflow UI → s08_caop_ingestion → Trigger DAG w/ config:
    {
        "version": "2024",
        "download_url": "<direct .gpkg URL from DGT CAOP page>"
    }
"""

from pipelines.gis.caop.caop_config import CAOP_CONFIG
from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag

dag = create_gis_ingestion_dag(CAOP_CONFIG)
