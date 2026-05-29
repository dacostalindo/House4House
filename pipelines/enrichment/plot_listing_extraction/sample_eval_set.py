"""
Sample a stratified 50-listing eval set for Slice C LLM plot extraction.

Reads from `staging_dbt.stg_plot_listings` (Aveiro + Coimbra concelhos,
~403 active rows), buckets each listing by extraction difficulty, samples
deterministically (seed=42), and writes a JSONL skeleton to
`tests/fixtures/plot_listings_eval.jsonl` for hand-labeling.

Stratification (per concelho, 25 each → 50 total):
  - 12 "has_numeric"  — m² mention or "área de construção" hit. Tests
    happy path of numeric extraction.
  -  8 "fluff"        — no m² mention at all. Tests null-handling
    (all numeric fields should resolve to null).
  -  5 "edge_case"    — ranges ("200 a 300 m²"), multi-lot ("lotes 1, 2 e 3"),
    or per-floor breakdowns ("100m² por piso"). Stress-tests parsing.

Output JSONL row shape:
    {
      "listing_id": "...",
      "concelho_slug": "aveiro" | "coimbra",
      "description": "...",
      "listing_url": "...",
      "bronze_lot_size": float | null,
      "expected": {<all-null shell matching the Pydantic schema>},
      "candidates": {"m2_mentions": [...]}  // regex pre-fills for labelers
    }

All 50 entries ship with null `expected` fields — the hand-labeling pass
(Task 4) fills them. Pre-labels were considered and rejected to avoid
anchoring bias.

CLI:
  Inside Airflow container:
    python -m pipelines.enrichment.plot_listing_extraction.sample_eval_set
  From host (warehouse on localhost:5433):
    WAREHOUSE_HOST=localhost WAREHOUSE_PORT=5433 \\
      python pipelines/enrichment/plot_listing_extraction/sample_eval_set.py
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path

import psycopg2

# Deterministic sample — re-running the script reproduces the same 50 rows.
SAMPLE_SEED = 42

# Per-concelho stratification targets. Sum per concelho = 25; total 50.
PER_CONCELHO_TARGETS: dict[str, int] = {
    "has_numeric": 12,
    "fluff": 8,
    "edge_case": 5,
}

CONCELHOS: tuple[str, ...] = ("aveiro", "coimbra")

OUT_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "plot_listings_eval.jsonl"


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

# Explicit "área de construção" / "área bruta de construção" / variants.
REGEX_AREA_DE_CONSTRUCAO = re.compile(
    r"área(\s+bruta)?\s+de\s+constr[uçãoíi]+", re.IGNORECASE
)

# Any "<number> m²" mention (also matches "m2"). Trailing word boundary
# omitted because Python re considers ² a non-word character on some locales.
REGEX_M2 = re.compile(
    r"(\d{1,3}(?:[\s.,]\d{3})*(?:,\d+)?|\d+(?:,\d+)?)\s*m[2²]",
    re.IGNORECASE,
)

# Edge-case heuristics: ranges, multi-lot, per-floor breakdown.
REGEX_RANGE = re.compile(r"\d+\s+(a|até|entre)\s+\d+\s*m[2²]", re.IGNORECASE)
REGEX_MULTI_LOT = re.compile(r"lotes\s+\d", re.IGNORECASE)
REGEX_PER_FLOOR = re.compile(r"\b(por|cada)\s+piso\b|\bpiso[s]?\b.{0,40}m[2²]", re.IGNORECASE)


def categorize(description: str) -> str:
    """Bucket a listing into one of: has_numeric, fluff, edge_case."""
    has_m2 = REGEX_M2.search(description) is not None
    has_area = REGEX_AREA_DE_CONSTRUCAO.search(description) is not None
    is_edge = (
        REGEX_RANGE.search(description) is not None
        or REGEX_MULTI_LOT.search(description) is not None
        or REGEX_PER_FLOOR.search(description) is not None
    )

    if is_edge and (has_m2 or has_area):
        return "edge_case"
    if has_m2 or has_area:
        return "has_numeric"
    return "fluff"


def extract_m2_candidates(description: str) -> list[str]:
    """Surface every '<number> m²' substring to seed labeler review."""
    return [m.group(0).strip() for m in REGEX_M2.finditer(description)]


# ---------------------------------------------------------------------------
# Warehouse fetch
# ---------------------------------------------------------------------------


def _connect():
    """Connect to the warehouse. WAREHOUSE_HOST default is the docker service
    name ('warehouse'); set to 'localhost' + WAREHOUSE_PORT=5433 to run from
    the host machine."""
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "warehouse"),
        port=int(os.environ.get("WAREHOUSE_PORT", "5432")),
        dbname=os.environ.get("WAREHOUSE_DB", "house4house"),
        user=os.environ.get("WAREHOUSE_USER", "warehouse"),
        password=os.environ.get("WAREHOUSE_PASSWORD", "warehouse2025house4house"),
    )


def fetch_listings() -> list[dict]:
    """Pull all stg_plot_listings rows. Returns dicts keyed by column name."""
    query = """
        SELECT listing_id, concelho_slug, description, listing_url, lot_size
        FROM staging_dbt.stg_plot_listings
        ORDER BY listing_id
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------


def stratified_sample(
    rows: list[dict],
    targets: dict[str, int],
    concelhos: tuple[str, ...],
    seed: int,
) -> list[dict]:
    """Sample N per (concelho, bucket). Falls back to oversampling other
    buckets within the same concelho if the target bucket is short."""
    rng = random.Random(seed)
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        bucket = categorize(row["description"])
        row["_bucket"] = bucket
        by_key.setdefault((row["concelho_slug"], bucket), []).append(row)

    selected: list[dict] = []
    for concelho in concelhos:
        for bucket, n_target in targets.items():
            pool = by_key.get((concelho, bucket), [])
            if len(pool) < n_target:
                print(
                    f"WARNING: {concelho}/{bucket} has {len(pool)} rows, "
                    f"target {n_target} — using all available.",
                    file=sys.stderr,
                )
            n = min(n_target, len(pool))
            sample = rng.sample(pool, n) if n > 0 else []
            selected.extend(sample)

        # Backfill the concelho to 25 if any bucket was short.
        target_per_concelho = sum(targets.values())
        already_selected_ids = {r["listing_id"] for r in selected}
        already_this_concelho = sum(1 for r in selected if r["concelho_slug"] == concelho)
        gap = target_per_concelho - already_this_concelho
        if gap > 0:
            backfill_pool = [
                r
                for r in rows
                if r["concelho_slug"] == concelho
                and r["listing_id"] not in already_selected_ids
            ]
            if backfill_pool:
                n_backfill = min(gap, len(backfill_pool))
                selected.extend(rng.sample(backfill_pool, n_backfill))
                print(
                    f"INFO: backfilled {n_backfill} extra {concelho} rows "
                    f"to hit the 25-per-concelho target.",
                    file=sys.stderr,
                )

    return selected


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


EXPECTED_SHELL: dict[str, None] = {
    "parcel_area_m2": None,
    "implantation_area_m2": None,
    "construction_area_m2_above_ground": None,
    "construction_area_m2_total": None,
    "num_dwellings_allowed": None,
    "max_height_m": None,
    "permit_status": None,
    "is_loteamento": None,
}


def to_jsonl_entry(row: dict) -> dict:
    return {
        "listing_id": row["listing_id"],
        "concelho_slug": row["concelho_slug"],
        "description": row["description"],
        "listing_url": row["listing_url"],
        "bronze_lot_size": float(row["lot_size"]) if row["lot_size"] is not None else None,
        "expected": EXPECTED_SHELL.copy(),
        "candidates": {"m2_mentions": extract_m2_candidates(row["description"])},
        "_bucket": row.get("_bucket"),
    }


def write_jsonl(entries: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    rows = fetch_listings()
    print(f"Fetched {len(rows)} rows from staging_dbt.stg_plot_listings.", file=sys.stderr)

    sampled = stratified_sample(rows, PER_CONCELHO_TARGETS, CONCELHOS, SAMPLE_SEED)
    print(
        f"Sampled {len(sampled)} rows "
        f"({sum(1 for r in sampled if r['concelho_slug']=='aveiro')} Aveiro / "
        f"{sum(1 for r in sampled if r['concelho_slug']=='coimbra')} Coimbra).",
        file=sys.stderr,
    )

    # Stable order across re-runs: by concelho then listing_id.
    sampled.sort(key=lambda r: (r["concelho_slug"], r["listing_id"]))
    entries = [to_jsonl_entry(r) for r in sampled]

    write_jsonl(entries, OUT_PATH)
    print(f"Wrote {len(entries)} entries to {OUT_PATH}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
