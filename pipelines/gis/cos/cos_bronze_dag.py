"""
COS 2023 Bronze Loading

Loads COS 2023 GeoPackage from MinIO into PostGIS bronze table.
Single layer, ~842K polygons with 4-level land-use classification.

Instantiated from the GPKG bronze template using COS-specific config.
To trigger: Airflow UI → cos2023_bronze_load → Trigger DAG
"""

from pipelines.gis.template.gpkg_bronze_template import (
    GpkgBronzeConfig,
    GpkgLayerConfig,
    create_gpkg_bronze_dag,
)

COS_BRONZE_CONFIG = GpkgBronzeConfig(
    dag_id="cos2023_bronze_load",
    source_name="cos",
    description=(
        "Load COS 2023 land-use GeoPackage from MinIO into PostGIS. "
        "~784K polygons with 4-level hierarchical classification."
    ),
    minio_prefix="cos",
    layers=[
        GpkgLayerConfig(
            gpkg_layer="COS2023v1",
            table="bronze_geo.raw_cos2023",
            fields=[
                # GPKG columns: ID, COS23_n4_C, COS23_n4_L, AREA_ha
                # PostgreSQL lowercases: id, cos23_n4_c, cos23_n4_l, area_ha
                ("id", "INTEGER"),
                ("cos23_n4_c", "VARCHAR(10)"),
                ("cos23_n4_l", "TEXT"),
                ("area_ha", "DOUBLE PRECISION"),
            ],
            geom_type="MULTIPOLYGON",
            expected_min=500_000,
            indexes=["cos23_n4_c"],
        ),
    ],
    read_batch_size=5000,
    dbt_trigger_dag_id="dbt_cos_build",
    tags=["cos", "land-use", "dgt"],
)

dag = create_gpkg_bronze_dag(COS_BRONZE_CONFIG)
