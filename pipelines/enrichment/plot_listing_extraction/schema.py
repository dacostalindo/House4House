"""
Plot listing extraction — LLM extraction contract for idealista plot listings.

Used by `plot_listing_extraction_dag.py` to coerce Claude Haiku 4.5 structured
output into a typed shape. The DAG writes one row per listing into
`bronze_enrichment.raw_plot_listing_extractions` per the bronze-permissive
rule (no validation in bronze itself; this Pydantic shape governs the
LLM coercion only).

Field-axis split:
  Numeric m² (text-extracted):
    implantation_area_m2                 — Impl.
    construction_area_m2_above_ground    — ABC Sol
    construction_area_m2_total           — ABC T  (headline / demo metric)
    area_loteamento_m2                   — Total subdivision area (when is_loteamento)

  Counts:
    num_dwellings_allowed                — # de Fogos
    max_floors_allowed                   — Nº pisos / andares (R/C counts as 1)
    num_caves                            — Number of basement / cave levels

  Categorical (text-extracted, two orthogonal axes):
    permit_status   — progression: project_approved > project_drafted > pip
    is_loteamento   — subdivision flag, independent of permit_status

  Provenance:
    source_spans    — field_name → exact sentence(s) backing the value

NOT extracted by the LLM:
  parcel_area_m2 — comes from bronze `lot_size` (structured listing field).
                   Per user 2026-05-29: text-only rule means parcel area
                   stays out of LLM scope. Silver model uses bronze lot_size
                   directly. The 30/40 match rate between human labels and
                   bronze across the eval set confirmed parcel is structured
                   data, not prose extraction.

Derived fields (NOT extracted; computed in silver):
    construction_index_derived = construction_area_m2_total / bronze.lot_size
    implantation_pct_derived   = implantation_area_m2 / bronze.lot_size * 100

DAG-side metadata fields, attached around the schema in the bronze row:
    extraction_confidence  — self-eval second call, clamped to [0.0, 1.0]
    extraction_status      — 'success' | 'failed'
    error_message          — populated when status='failed'
    raw_response           — populated when status='failed'

V4 → V5 changes (2026-05-29):
  - Removed `parcel_area_m2` — bronze lot_size is authoritative.
  - Removed `max_height_m` (already gone in V4 — `max_floors_allowed`).
  - permit_status Literal narrowed: `["pip","project_drafted","project_approved"]`.
    Dropped `without_pip` (null is the absence marker). Split `project` into
    drafted vs approved per user feedback on case 29.
  - Added `num_caves: int | None` — PT listings frequently spell out basement
    parking levels separately ("2 caves").
  - Added `area_loteamento_m2: float | None` — total subdivision area when
    is_loteamento=true (cases 37 + 39 surfaced the need).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PermitStatus = Literal["pip", "project_drafted", "project_approved"]


class PlotListingExtraction(BaseModel):
    """LLM-coerced shape for a single idealista plot listing."""

    model_config = ConfigDict(extra="forbid")

    # ------------------------------------------------------------------
    # Numeric m² (text-extracted)
    # ------------------------------------------------------------------
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
    area_loteamento_m2: float | None = Field(
        default=None,
        description=(
            "Total area of the loteamento (subdivision) in m², when "
            "is_loteamento=true. Typically the sum of the individual lot areas "
            "(e.g. 'áreas dos lotes: 6.029m2') or the area covered by the "
            "licença de urbanização. Null when is_loteamento != true OR when "
            "the listing doesn't quantify the subdivision area."
        ),
    )

    # ------------------------------------------------------------------
    # Counts (integers)
    # ------------------------------------------------------------------
    num_dwellings_allowed: int | None = Field(
        default=None,
        description="# de Fogos — count of dwellings allowed by the planning instrument.",
    )
    max_floors_allowed: int | None = Field(
        default=None,
        description=(
            "Maximum allowed number of floors / 'pisos' / 'andares' the parcel "
            "permits. R/C ('rés-do-chão', ground floor) counts as 1. "
            "Examples: 'R/C + 2 andares' = 3; 'até 4 pisos' = 4; "
            "'máximo 5 andares' = 5. Floors (not height in metres) is the "
            "planning signal PT developers actually use for valuation."
        ),
    )
    num_caves: int | None = Field(
        default=None,
        description=(
            "Number of basement / cave levels. Typically 0, 1, or 2 in PT "
            "real estate. Examples: '1 cave' = 1; '2 caves para estacionamento' "
            "= 2; '3 pisos abaixo da cota de soleira' = 3. Null when the "
            "listing does not mention basements."
        ),
    )

    # ------------------------------------------------------------------
    # Categorical — two orthogonal axes (Finding 1E)
    # ------------------------------------------------------------------
    permit_status: PermitStatus | None = Field(
        default=None,
        description=(
            "Permit progression for the parcel. Most-advanced state wins when "
            "the description mentions multiple: "
            "  project_approved > project_drafted > pip > null.\n"
            "Values:\n"
            "  - 'project_approved' = 'projeto aprovado' / 'alvará' / explicitly "
            "    approved by the câmara municipal.\n"
            "  - 'project_drafted'  = 'tem projeto' / 'projeto de arquitetura "
            "    não submetido' / project drawn up but not approved.\n"
            "  - 'pip'              = PIP (pedido de informação prévia) "
            "    submitted, in approval, or approved. Includes 'PIP em fase "
            "    final de aprovação'.\n"
            "  - null               = description does not mention any permit "
            "    state. The absence of mention is null; do not infer "
            "    'without_pip' as a separate state."
        ),
    )
    is_loteamento: bool | None = Field(
        default=None,
        strict=True,
        description=(
            "Whether the parcel is part of a loteamento (subdivision). "
            "True = description mentions 'loteamento' / 'alvará de loteamento' / "
            "'licença de urbanização' / explicit lots within an approved "
            "subdivision; "
            "False = description explicitly rules out subdivision; "
            "null = description does not mention. "
            "Orthogonal to permit_status — both fields populated independently."
        ),
    )

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------
    source_spans: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps each populated field name to the exact sentence in the source "
            "description that justifies the extracted value. "
            "Field names omitted from this dict correspond to null extractions."
        ),
    )
