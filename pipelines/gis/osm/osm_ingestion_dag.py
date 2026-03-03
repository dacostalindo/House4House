"""
OSM Ingestion DAG — S09 POIs, S10 Transport, S11 Roads

Instantiated from the GIS ingestion template using OSM-specific config.
All pipeline logic lives in the template; all OSM specifics live in osm_config.py.

To trigger: Airflow UI → s09_osm_ingestion → Trigger DAG w/ config
    {"version": "2026-03"}
"""

from pipelines.gis.osm.osm_config import OSM_CONFIG
from pipelines.gis.template.gis_ingestion_template import create_gis_ingestion_dag

dag = create_gis_ingestion_dag(OSM_CONFIG)
