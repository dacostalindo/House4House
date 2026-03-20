"""
BUPI Bronze Loading

Loads BUPI GeoPackage from MinIO into PostGIS bronze table.
Single layer (auto-detected), ~3.25M property parcels with parish codes.

Instantiated from the GPKG bronze template using BUPI-specific config.
To trigger: Airflow UI → bupi_bronze_load → Trigger DAG
"""

from pipelines.gis.template.gpkg_bronze_template import (
    GpkgBronzeConfig,
    GpkgLayerConfig,
    create_gpkg_bronze_dag,
)

BUPI_BRONZE_CONFIG = GpkgBronzeConfig(
    dag_id="bupi_bronze_load",
    source_name="bupi",
    description=(
        "Load BUPI simplified cadastral GeoPackage from MinIO into PostGIS. "
        "~3.25M property parcels with parish codes and area."
    ),
    minio_prefix="bupi",
    layers=[
        GpkgLayerConfig(
            gpkg_layer=None,  # auto-detect (layer name includes date)
            table="bronze_regulatory.raw_bupi",
            fields=[
                # GPKG columns: ProcessoId, NumeroMatriz, Dicofre, Concelho, Freguesia, Area_m2
                # PostgreSQL lowercases: processoid, numeromatriz, dicofre, concelho, freguesia, area_m2
                ("processoid", "INTEGER"),
                ("numeromatriz", "TEXT"),
                ("dicofre", "VARCHAR(6)"),
                ("concelho", "TEXT"),
                ("freguesia", "TEXT"),
                ("area_m2", "DOUBLE PRECISION"),
            ],
            geom_type="MULTIPOLYGON",
            expected_min=2_500_000,
            indexes=["dicofre", "concelho"],
        ),
    ],
    read_batch_size=5000,
    dbt_trigger_dag_id="dbt_bupi_build",
    tags=["bupi", "cadastro", "property", "bronze", "postgis"],
)

dag = create_gpkg_bronze_dag(BUPI_BRONZE_CONFIG)
