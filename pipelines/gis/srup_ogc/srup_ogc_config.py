# v2 scope — preserved from .pyc decompile. Day-8 evaluation gate: may
# be promoted into v1 wedge parcel_constraints.sql per the Sprint-08 plan.
# See wiki/sources/srup-ogc.md for the canonical source spec.

"""
SRUP OGC API Ingestion Configuration

Data source: DGTERRITÓRIO SRUP via the public OGC API at
`https://ogcapi.dgterritorio.gov.pt/collections/{id}/items`.

This module is the WS2a/b registry for SRUP layers that have moved (or are moving)
from the legacy WFS endpoints (`servicos.dgterritorio.pt/SDISNITWFS*`) to the
modern OGC API. The legacy WFS pipeline (`pipelines/gis/srup/srup_*`) continues
to serve IC + DPH while we migrate everything else here.

WS2a (Week 2) — 12 layer configs:
  REN×2 (gates):              srup_ren_areal, srup_ren_linear
  Áreas Protegidas:           srup_areas_protegidas (gate-vs-soft via attribute filter in dbt)
  Natura 2000 ×2 (soft):      srup_zpe, srup_zec
  Defesa militar ×2:          srup_defesa_militar (gate), srup_defesa_militar_zonas (soft)
  Layer 3 risk:               srup_perigosidade_inc_rural
  SGIFR ×3 (fire defense):    sgifr_areas, sgifr_linhas, sgifr_pontos
  RAN dual-run:               srup_ran (OGC parity vs legacy WFS — see dual-run macro)

WS2b (Week 3) layers — added in a separate config registry alongside this one.

--- Naming convention ---
Each config produces:
  - one entry in MinIO under raw/srup_ogc/{name}/{YYYYMMDD}/{name}.geojson
  - one bronze table:  bronze_regulatory.raw_{name}
  - one dbt staging model: stg_{name}.sql

For the RAN dual-run, the OGC version writes to `bronze_regulatory.raw_srup_ran_ogc`
to coexist with the legacy `raw_srup_ran` (WFS) for parity validation.

--- License + attribution ---
Source: DGTERRITÓRIO. Per the OGC API terms, redistribution permitted with attribution.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

OGCAPI_BASE = "https://ogcapi.dgterritorio.gov.pt/collections"

SOURCE_SRID = 3763

PAGE_SIZE = 1000
REQUEST_DELAY_SECONDS: float = 1.0
REQUEST_TIMEOUT_SECONDS: int = 120


class SRUPOGCLayerConfig(BaseModel):
    """Configuration for a single SRUP collection at the DGT OGC API.

    name:
        canonical identifier used as MinIO prefix, bronze table suffix, and
        dbt staging model filename. Example: 'srup_ren_areal'.

    collection_id:
        OGC API collection ID at ogcapi.dgterritorio.gov.pt. Usually the same
        as `name` but kept separate for cases where the OGC ID differs from
        the bronze table name (e.g. SGIFR layers don't carry the 'srup_' prefix
        upstream, but we name our bronze tables consistently).

    bronze_table:
        Fully-qualified target bronze table.

    label:
        Human-readable description, used in logs.

    layer_role:
        Categorization for the assessment view:
            'gate'       — Layer 0 hard gate; intersection blocks construction
            'soft'       — Layer 3 soft constraint; surfaces in soft_constraint_flags
            'attr_split' — Single OGC layer that contains both gates and softs;
                           the dbt staging model splits via attribute filter
            'risk'       — Layer 3 risk class (e.g. wildfire_class)
            'driver'     — Layer 2 driver (e.g. networks for distance KNN)

    expected_min_features:
        Minimum national row count for sanity validation (hard fail if breached).
        Set conservatively — the goal is to catch "0 features returned" type
        failures, not enforce exact counts.

    page_size_override:
        Per-layer page_size override for the OGC API pagination. None = use the
        global PAGE_SIZE default (1000). Lowered to 50-100 for layers with very
        large polygon geometries where the upstream gateway times out on
        large pages — empirically this is REN areal/linear, RAN, and
        perigosidade_inc_rural at high offsets. Lesson learned 2026-05-04
        during the WS2a live ingest: the OGC API hangs forever on
        `limit=1000` for these layers (probably proxy buffering or per-page
        serialization timeout).

    request_timeout_override:
        Per-layer request timeout override in seconds. None = use the global
        REQUEST_TIMEOUT_SECONDS default. Useful for layers known to be slow.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    collection_id: str
    bronze_table: str
    label: str
    layer_role: str
    expected_min_features: int = 1
    page_size_override: int | None = None
    request_timeout_override: int | None = None


SRUP_OGC_LAYERS: list[SRUPOGCLayerConfig] = [
    # --- REN ×2 (gates) ---
    SRUPOGCLayerConfig(
        name="srup_ren_areal",
        collection_id="srup_ren_areal",
        bronze_table="bronze_regulatory.raw_srup_ren_areal",
        label="REN — Reserva Ecológica Nacional, Áreas",
        layer_role="gate",
        expected_min_features=100,
        page_size_override=10,
        request_timeout_override=300,
    ),
    SRUPOGCLayerConfig(
        name="srup_ren_linear",
        collection_id="srup_ren_linear",
        bronze_table="bronze_regulatory.raw_srup_ren_linear",
        label="REN — Reserva Ecológica Nacional, Linhas",
        layer_role="gate",
        expected_min_features=10,
        page_size_override=50,
    ),
    # --- Áreas Protegidas (cores + buffers via attr_split) ---
    SRUPOGCLayerConfig(
        name="srup_areas_protegidas",
        collection_id="srup_areas_protegidas",
        bronze_table="bronze_regulatory.raw_srup_areas_protegidas",
        label="Áreas Protegidas (cores + buffers)",
        layer_role="attr_split",
        expected_min_features=20,
    ),
    # --- Rede Natura 2000 (soft) ---
    SRUPOGCLayerConfig(
        name="srup_zpe",
        collection_id="srup_zpe",
        bronze_table="bronze_regulatory.raw_srup_zpe",
        label="Rede Natura 2000 — Zonas de Proteção Especial (Birds Directive)",
        layer_role="soft",
        expected_min_features=20,
    ),
    SRUPOGCLayerConfig(
        name="srup_zec",
        collection_id="srup_zec",
        bronze_table="bronze_regulatory.raw_srup_zec",
        label="Rede Natura 2000 — Zonas Especiais de Conservação (Habitats Directive)",
        layer_role="soft",
        expected_min_features=20,
    ),
    # --- Defesa militar (gate + soft) ---
    SRUPOGCLayerConfig(
        name="srup_defesa_militar",
        collection_id="srup_defesa_militar",
        bronze_table="bronze_regulatory.raw_srup_defesa_militar",
        label="Defesa Nacional — Áreas de Defesa Militar",
        layer_role="gate",
        expected_min_features=1,
    ),
    SRUPOGCLayerConfig(
        name="srup_defesa_militar_zonas",
        collection_id="srup_defesa_militar_zonas",
        bronze_table="bronze_regulatory.raw_srup_defesa_militar_zonas",
        label="Defesa Nacional — Zonas de proteção de defesa militar",
        layer_role="soft",
        expected_min_features=1,
    ),
    # --- Layer 3 risk: wildfire ---
    SRUPOGCLayerConfig(
        name="srup_perigosidade_inc_rural",
        collection_id="srup_perigosidade_inc_rural",
        bronze_table="bronze_regulatory.raw_srup_perigosidade_inc_rural",
        label="Carta de Perigosidade de Incêndio Rural (ICNF)",
        layer_role="risk",
        expected_min_features=100,
        page_size_override=500,
        request_timeout_override=300,
    ),
    # --- SGIFR ×3 (soft — fire-defense ops) ---
    SRUPOGCLayerConfig(
        name="srup_sgifr_areas",
        collection_id="sgifr_areas",
        bronze_table="bronze_regulatory.raw_srup_sgifr_areas",
        label="SGIFR — Sistemas de Gestão Integrada de Fogos Rurais, Áreas",
        layer_role="soft",
        expected_min_features=20,
    ),
    SRUPOGCLayerConfig(
        name="srup_sgifr_linhas",
        collection_id="sgifr_linhas",
        bronze_table="bronze_regulatory.raw_srup_sgifr_linhas",
        label="SGIFR — Sistemas de Gestão Integrada de Fogos Rurais, Linhas",
        layer_role="soft",
        expected_min_features=10,
    ),
    SRUPOGCLayerConfig(
        name="srup_sgifr_pontos",
        collection_id="sgifr_pontos",
        bronze_table="bronze_regulatory.raw_srup_sgifr_pontos",
        label="SGIFR — Sistemas de Gestão Integrada de Fogos Rurais, Pontos",
        layer_role="soft",
        expected_min_features=10,
    ),
    # --- RAN OGC dual-run vs legacy WFS ---
    SRUPOGCLayerConfig(
        name="srup_ran_ogc",
        collection_id="srup_ran",
        bronze_table="bronze_regulatory.raw_srup_ran_ogc",
        label="RAN — Reserva Agrícola Nacional (OGC dual-run vs WFS)",
        layer_role="gate",
        expected_min_features=100,
        page_size_override=20,
        request_timeout_override=300,
    ),
    # --- Árvores de Interesse Público ---
    SRUPOGCLayerConfig(
        name="srup_arvores_areal",
        collection_id="srup_arvores_areal",
        bronze_table="bronze_regulatory.raw_srup_arvores_areal",
        label="Árvores de Interesse Público — Áreas",
        layer_role="soft",
        expected_min_features=10,
    ),
    SRUPOGCLayerConfig(
        name="srup_arvores_point",
        collection_id="srup_arvores_point",
        bronze_table="bronze_regulatory.raw_srup_arvores_point",
        label="Árvores de Interesse Público — Pontos",
        layer_role="soft",
        expected_min_features=50,
    ),
    # --- Marcos Geodésicos (informational only) ---
    SRUPOGCLayerConfig(
        name="srup_marcos_geod",
        collection_id="srup_marcos_geod",
        bronze_table="bronze_regulatory.raw_srup_marcos_geod",
        label="Marcos Geodésicos (informational, building exclusion buffer)",
        layer_role="soft",
        expected_min_features=1000,
    ),
    # --- Servidões aeronáuticas (height limits) ---
    SRUPOGCLayerConfig(
        name="srup_aeronautica",
        collection_id="srup_aeronautica",
        bronze_table="bronze_regulatory.raw_srup_aeronautica",
        label="Servidões aeronáuticas — limites de altura derivados",
        layer_role="soft",
        expected_min_features=5,
    ),
    # --- Aquíferos (groundwater protection) ---
    SRUPOGCLayerConfig(
        name="srup_aquiferos",
        collection_id="srup_aquiferos",
        bronze_table="bronze_regulatory.raw_srup_aquiferos",
        label="Captação de águas subterrâneas — proteção de aquíferos",
        layer_role="soft",
        expected_min_features=100,
    ),
    # --- Albufeiras de águas públicas ---
    SRUPOGCLayerConfig(
        name="srup_albufeiras",
        collection_id="srup_albufeiras",
        bronze_table="bronze_regulatory.raw_srup_albufeiras",
        label="Albufeiras de águas públicas classificadas",
        layer_role="soft",
        expected_min_features=10,
        page_size_override=50,
        request_timeout_override=300,
    ),
    # --- Layer 2 drivers (networks) ---
    SRUPOGCLayerConfig(
        name="srup_rede_viaria",
        collection_id="srup_rede_viaria",
        bronze_table="bronze_regulatory.raw_srup_rede_viaria",
        label="Rede Rodoviária Nacional (Layer 2 access driver)",
        layer_role="driver",
        expected_min_features=500,
        page_size_override=200,
    ),
    SRUPOGCLayerConfig(
        name="srup_rede_ferroviaria",
        collection_id="srup_rede_ferroviaria",
        bronze_table="bronze_regulatory.raw_srup_rede_ferroviaria",
        label="Rede Ferroviária — linhas",
        layer_role="driver",
        expected_min_features=50,
        page_size_override=100,
    ),
    SRUPOGCLayerConfig(
        name="srup_rede_ferroviaria_estacoes",
        collection_id="srup_rede_ferroviaria_estacoes",
        bronze_table="bronze_regulatory.raw_srup_rede_ferroviaria_estacoes",
        label="Rede Ferroviária — estações",
        layer_role="driver",
        expected_min_features=100,
    ),
    SRUPOGCLayerConfig(
        name="srup_rede_eletrica",
        collection_id="srup_rede_eletrica",
        bronze_table="bronze_regulatory.raw_srup_rede_eletrica",
        label="Rede Elétrica (Layer 2 utility driver)",
        layer_role="driver",
        expected_min_features=500,
    ),
]


SRUP_OGC_BY_NAME: dict[str, SRUPOGCLayerConfig] = {layer.name: layer for layer in SRUP_OGC_LAYERS}


MINIO_BUCKET = "raw"
MINIO_PREFIX_BASE = "srup_ogc"


def minio_prefix_for(layer: SRUPOGCLayerConfig) -> str:
    """Build the MinIO prefix for a layer."""
    return f"{MINIO_PREFIX_BASE}/{layer.name}"


class SRUPOGCIngestionConfig(BaseModel):
    """Top-level config for the omnibus SRUP OGC ingestion + bronze DAGs."""

    ingestion_dag_id: str = "srup_ogc_ingestion"
    bronze_dag_id: str = "srup_ogc_bronze_load"

    description_ingestion: str = (
        "SRUP OGC API ingestion — fetches all WS2a SRUP layers from "
        "ogcapi.dgterritorio.gov.pt and writes GeoJSON to MinIO."
    )
    description_bronze: str = (
        "SRUP OGC bronze loader — loads per-layer GeoJSON from MinIO into "
        "per-layer bronze tables under bronze_regulatory."
    )

    page_size: int = PAGE_SIZE
    request_delay_seconds: float = REQUEST_DELAY_SECONDS
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS

    schedule: str | None = None
    start_date: datetime = Field(default_factory=lambda: datetime(2026, 5, 1))
    max_active_runs: int = 1
    max_active_tasks: int = 4
    trigger_dbt_dag_id: str | None = "dbt_srup_build"

    tags: list[str] = Field(default_factory=lambda: ["srup", "ogc_api", "constraints"])
    retries: int = 2
    retry_delay_minutes: int = 5


SRUP_OGC_CONFIG = SRUPOGCIngestionConfig()
