"""
Plot listing extraction — LLM extraction contract for idealista plot listings.

Used by `plot_listing_extraction_dag.py` to coerce Claude Haiku 4.5 structured
output into a typed shape. The DAG writes one row per listing into
`bronze_enrichment.raw_plot_listing_extractions` per the bronze-permissive
rule (no validation in bronze itself; this Pydantic shape governs the
LLM coercion only).

Field-axis split:
  Numeric (text-extracted):
    parcel_area_m2                       — Terreno
    implantation_area_m2                 — Impl.
    construction_area_m2_above_ground    — ABC Sol
    construction_area_m2_total           — ABC T  (headline / demo metric)
    num_dwellings_allowed                — # de Fogos
    max_height_m

  Categorical (text-extracted, two orthogonal axes):
    permit_status   — progression: project > pip > without_pip
    is_loteamento   — subdivision flag, independent of permit_status

  Provenance:
    source_spans    — field_name → exact sentence(s) backing the value

Derived fields (NOT extracted; computed in silver):
    construction_index_derived = construction_area_m2_total / parcel_area_m2
    implantation_pct_derived   = implantation_area_m2 / parcel_area_m2 * 100

DAG-side metadata fields, attached around the schema in the bronze row:
    extraction_confidence  — self-eval second call, clamped to [0.0, 1.0]
    extraction_status      — 'success' | 'failed'
    error_message          — populated when status='failed'
    raw_response           — populated when status='failed'
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PermitStatus = Literal["project", "pip", "without_pip"]


class PlotListingExtraction(BaseModel):
    """LLM-coerced shape for a single idealista plot listing."""

    parcel_area_m2: float | None = Field(
        default=None,
        description="Terreno — total parcel area in m². Cross-validated against bronze lot_size.",
    )
    implantation_area_m2: float | None = Field(
        default=None,
        description="Impl. — building footprint on the parcel in m².",
    )
    construction_area_m2_above_ground: float | None = Field(
        default=None,
        description="ABC Sol — above-ground gross built area in m².",
    )
    construction_area_m2_total: float | None = Field(
        default=None,
        description="ABC T — total gross built area in m², including basement / cave.",
    )
    num_dwellings_allowed: int | None = Field(
        default=None,
        description="# de Fogos — count of dwellings allowed by the planning instrument.",
    )
    max_height_m: float | None = Field(
        default=None,
        description="Maximum building height in metres.",
    )

    permit_status: PermitStatus | None = Field(
        default=None,
        description=(
            "Permit progression for the parcel: "
            "'project' = approved construction project / alvará; "
            "'pip' = pedido de informação prévia (preliminary planning enquiry) approved; "
            "'without_pip' = description states no permit / no project; "
            "null = description does not mention permit status. "
            "Tiebreak when multiple states are mentioned: most-advanced wins "
            "(project > pip > without_pip)."
        ),
    )
    is_loteamento: bool | None = Field(
        default=None,
        strict=True,
        description=(
            "Whether the parcel is part of an approved loteamento (subdivision). "
            "True = description explicitly mentions 'loteamento' / 'lote em loteamento aprovado'; "
            "False = description rules out subdivision; "
            "null = description does not mention. "
            "Orthogonal to permit_status — both fields are populated independently."
        ),
    )

    source_spans: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps each populated field name to the exact sentence in the source "
            "description that justifies the extracted value. "
            "Field names omitted from this dict correspond to null extractions."
        ),
    )
