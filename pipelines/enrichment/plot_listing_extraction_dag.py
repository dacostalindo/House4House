"""Plot listing extraction DAG — Sprint-09 Slice C.

Sits as a manual-trigger DAG between `idealista_bronze_load` and
`dbt_idealista_build` for plot listings:

    idealista_bronze_load
       → stg_plot_listings (Aveiro + Coimbra concelhos, 403 rows)
       → plot_listing_extraction (THIS DAG)
       → silver_plot_listings_enriched

For each plot listing in scope, calls Anthropic's Claude Sonnet 4.6 twice:

  1. Extraction — tool-use-forced structured output coerced into the
     PlotListingExtraction Pydantic schema (V5.1).
  2. Self-eval — a second call asking the model to rate its own confidence
     in the extraction on [0.0, 1.0]. Clamped defensively.

Reliability posture (post-2026-05-29 senior-eng review):
- Idempotency-hash check is per-row (SELECT before LLM call), not a single
  top-of-task read — protects against double-spend on concurrent manual
  triggers (UI-side race).
- Per-row Postgres reconnect on OperationalError keeps a 20-min run alive
  across transient warehouse blips.
- Cost-ceiling overshoot raises (not just logs WARNING) so the task fails
  loud and oncall doesn't see green on a partial backfill.
- Anthropic client has explicit 60s timeout; retries cover RateLimitError,
  APITimeoutError, APIConnectionError, InternalServerError. Self-eval
  failures are non-fatal but logged.

Writes one row per listing to `bronze_enrichment.raw_plot_listing_extractions`,
keyed by `idempotency_hash = sha256(listing_url + NFC(description).strip())`.
ON CONFLICT (idempotency_hash) DO NOTHING — re-runs only process listings
not yet extracted OR whose description text has changed since the last run.

Failure handling: on Anthropic API error after 3 retries OR Pydantic
validation failure, writes a sentinel row with `extraction_status='failed'`,
`error_message`, and `raw_response` captured. Gold layer filters
`extraction_status='success'`.

v1 scope (this DAG's WHERE clause): Aveiro + Coimbra concelhos, as filtered
by stg_plot_listings (~403 active rows). v1.5 expands to distritos, v2 to
national.

Manual trigger params (via dag_run.conf):
  - listing_ids:  list[str] | None — restrict to these listing_ids; null = all pending
  - max_cost_usd: float            — cost ceiling for this run (default 80.0)

Cost ~$0.008 per listing (extraction + self-eval on Haiku 4.5). Full
backfill of 403 rows ≈ $3.20.

See:
  - pipelines/enrichment/plot_listing_extraction/schema.py — PlotListingExtraction.
  - dbt/models/staging/portals/stg_plot_listings.sql — input.
  - dbt/models/silver/portals/silver_plot_listings_enriched.sql — downstream.
  - wiki/concepts/llm-plot-extraction.md — design rationale (added in Task 8).
"""

from __future__ import annotations

import logging
from datetime import datetime

from airflow.decorators import dag, task

log = logging.getLogger(__name__)


# Anthropic model + pricing constants (Sonnet 4.6 list price 2026-05-29).
# Was Haiku 4.5 in the initial implementation; eval-set comparison showed
# Haiku missed multiple thresholds (esp. ABC Sol vs ABC T disambiguation
# and R/C floor counting). Sonnet 4.6 is 3-4x more expensive but materially
# stronger on multi-field structured extraction. Decision 2026-05-29.
ANTHROPIC_MODEL = "claude-sonnet-4-6"
PRICE_INPUT_PER_MTOK = 3.00  # USD per 1M input tokens (Sonnet 4.6)
PRICE_OUTPUT_PER_MTOK = 15.00  # USD per 1M output tokens (Sonnet 4.6)

# Defaults — overridable via dag_run.conf.
DEFAULT_MAX_COST_USD = 80.0

# Retry tuning for transient Anthropic errors.
EXTRACTION_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 9.0)  # exponential


# ────────────────────────────────────────────────────────────────────────
# Prompts (kept inline so prompt-change CI gate (Task 6) can target this file)
# ────────────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a careful data-extraction assistant for Portuguese real-estate plot listings ("terrenos para construção").

Your job is to read an idealista plot listing description in Portuguese and call the `extract_plot_listing` tool with structured fields per the schema. Follow these rules.

═══════════════════════════════════════════════════════════════
GLOBAL RULE — SUBJECT-PARCEL ONLY
═══════════════════════════════════════════════════════════════

Only extract values that describe THIS parcel's allowed or planned construction.

DO NOT extract from text that describes:
  - Neighboring buildings, blocks already built nearby, or environmental context
    ("três blocos de apartamentos com rés-do-chão e mais três pisos" describing the
    SURROUNDINGS, not this plot → ignore for max_floors_allowed).
  - Existing constructions on adjacent properties.
  - Comparable projects in the area cited for marketing purposes.

The text typically introduces the subject parcel with verbs like "este terreno",
"o imóvel", "este lote", "a propriedade", "o presente terreno", or with project-
description language ("projeto aprovado para…", "PIP para a construção de…").
Confine extraction to those subject-anchored sentences.

═══════════════════════════════════════════════════════════════
NUMERIC FIELDS (m²) — extract literal text values only
═══════════════════════════════════════════════════════════════

  - implantation_area_m2 (Impl.): the building's footprint on the parcel.
    Sources: "área de implantação", "implantação".

  - construction_area_m2_above_ground (ABC Sol): ABOVE-GROUND gross built area only.
    Sources: any of:
      • "área bruta de construção" without explicit "total" qualifier;
      • "superfície edificável" / "capacidade construtiva";
      • a per-piso breakdown listing only above-ground floors (R/C + andares + sótão)
        — sum equals the figure quoted.
    EXAMPLE: "área bruta de construção 4010 m² distribuídos: 825 r/c, 910 1º, 910 2º,
    910 3º, 455 sótão" → above_ground = 4010 (the sum is above-ground only; cave
    referenced elsewhere belongs to num_caves, not the m² figures).

  - construction_area_m2_total (ABC T): TOTAL gross built area, including basement.
    Populate when ANY of these triggers is present:
      (a) Explicit "ABC T" / "área bruta total" / "área total de construção" /
          "área total construída" wording attached to a number.
      (b) "inclui cave" / "com cave" / "incluindo subsolo" attached to a number.
      (c) A breakdown where the figure explicitly sums BOTH above-ground floors AND
          basement m² values (e.g. "1500 m² = 200 cave + 1300 above").
      (d) A SINGLE BARE m² figure (no per-piso breakdown) appears together with
          a cave/subsolo/"pisos abaixo" mention in the SAME context (same paragraph
          or characteristics block). Example: "superfície edificável de 14 700 m²"
          appearing in a paragraph that also says "2 caves + R/C e 5 andares" →
          the 14 700 INCLUDES the caves → put it in total.
    If the description just says "área de construção 4010 m²" with a per-piso
    breakdown that lists ONLY above-ground floors → that goes to above_ground.
    If the description gives a single bare m² figure with NO cave/subsolo mention
    anywhere → that also goes to above_ground (default).
    Leave total NULL when none of the triggers fires AND no cave context exists.

  - area_loteamento_m2: total area of the subdivision (only when needs_loteamento=true).
    Sources: "áreas dos lotes", "área de loteamento", "Área total do loteamento".

DO NOT extract parcel area / "Terreno" / "área total do terreno" — that field is
removed from the schema; bronze structured data is authoritative for parcel size.

═══════════════════════════════════════════════════════════════
COUNTS (integer)
═══════════════════════════════════════════════════════════════

  - num_dwellings_allowed (# de Fogos): count of dwellings the planning instrument
    allows. Populate when description states an explicit count (e.g. "50 apartamentos",
    "14 fogos", "30 frações") or names a single dwelling type with implicit count
    ("moradia unifamiliar" = 1, "duas moradias geminadas" = 2). Loteamento lot-counts
    ("26 lotes destinados a habitação") map 1:1 to dwellings when habitação is named.

  - max_floors_allowed: ABOVE-GROUND floors only.
      • R/C ("rés-do-chão") counts as 1.
      • Caves / "Piso -1" / "subsolo" / "cota de soleira abaixo" do NOT count toward
        max_floors_allowed — they go to num_caves.
      • "Recuado" (recessed setback floor) does NOT count as a full floor — ignore it.
      • Single-figure text like "4 pisos (cave + 3)" → max_floors = 3 (the 3 above-ground),
        num_caves = 1.
      • "R/C, 1º, 2º, 3º andar e um recuado" → max_floors = 4 (R/C + 1 + 2 + 3, recuado
        does not add).
      • "moradia com cave, R/C e 1º andar" → max_floors = 2, num_caves = 1.

  - num_caves: number of basement / cave levels. Examples: "1 cave" = 1;
    "3 pisos abaixo da cota de soleira" = 3; "cave em -1 e -2" = 2.

═══════════════════════════════════════════════════════════════
CATEGORICAL — permit_status (4-value Literal; most-advanced wins; null when absent)
═══════════════════════════════════════════════════════════════

  - "project_approved" = "projeto aprovado" / "alvará" / explicitly approved.
  - "project_drafted"  = "tem projeto" / "projeto não submetido" / "projeto tipo" /
                         project drawn up but NOT approved.
  - "pip_approved"     = PIP explicitly approved ("PIP aprovado", "PIP favorável",
                         "parecer favorável", "que permite a construção").
  - "pip_pending"      = PIP submitted, in approval, or being processed
                         ("PIP em fase final de aprovação", "aguarda PIP",
                         "com PIP em análise").
  - null               = description does not mention permit state. Do NOT
                         infer "without_pip" as a value.

Tiebreak: project_approved > project_drafted > pip_approved > pip_pending.

═══════════════════════════════════════════════════════════════
CATEGORICAL — needs_loteamento + loteamento_complete (two bools, both orthogonal to permit_status)
═══════════════════════════════════════════════════════════════

`needs_loteamento` — does the planned development require this parcel to be
split into multiple legal lots?
  - true  = description implies MULTIPLE distinct buildings / moradias / blocos on
            the same parcel, OR explicitly mentions an existing loteamento /
            "licença de urbanização" covering multiple lots.
  - false = single-building plan with no subdivision implied (e.g. "moradia unifamiliar"
            with no additional construction).
  - null  = description does not address this dimension.

`loteamento_complete` — has the loteamento process / infrastructure already
been completed for this parcel?
  - true  = "alvará de loteamento (emitido / a pagamento)", "loteamento aprovado
            com infraestruturas", "licença de urbanização emitida", or lots that
            are already delimited and serviced.
  - false = description says loteamento is still pending / "precisa de loteamento"
            / "falta urbanização" / project-stage subdivision study not yet
            executed.
  - null  = needs_loteamento is false/null, OR the description does not address
            whether the subdivision work is done.

Examples:
  • "Single moradia, projeto aprovado" → needs=false, complete=null.
  • "Plot for 14 moradias, com alvará de loteamento" → needs=true, complete=true.
  • "Plot for 8 moradias, PIP em fase final" → needs=true, complete=false.
  • "Conjunto de 26 lotes destinados a habitação" → needs=true, complete=true (the
    26 lots already exist — the subdivision is done).

═══════════════════════════════════════════════════════════════
SOURCE_SPANS
═══════════════════════════════════════════════════════════════

For EVERY field you populate (non-null), include an entry in source_spans mapping the
field name to the exact sentence from the description that justifies the value. Omit
entries for fields you leave null.

═══════════════════════════════════════════════════════════════
GUARDRAILS
═══════════════════════════════════════════════════════════════

  - Marketing-fluff listings with no numbers → return null for all numeric / count
    fields and empty source_spans {}.
  - When in doubt between two values, prefer null. False positives are worse than null.
  - Do NOT invent values from analogy or aggregation. Only extract what the text states.
  - Do NOT compute totals across multiple parcels / lots / units — extract per-figure
    as the text presents it.
"""


# ────────────────────────────────────────────────────────────────────────
# DAG
# ────────────────────────────────────────────────────────────────────────


@dag(
    dag_id="plot_listing_extraction",
    description=(
        "LLM extraction of Portuguese plot listings via Claude Sonnet 4.6 "
        "(Pydantic-coerced structured output). Idempotent on "
        "sha256(url + NFC(description)). Manual trigger; "
        "v1 scope is Aveiro + Coimbra concelhos."
    ),
    schedule=None,  # manual / cost control
    start_date=datetime(2026, 5, 29),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data-engineering", "retries": 0, "retry_delay": 60},
    tags=["enrichment", "llm", "sonnet", "plot-listings"],
)
def plot_listing_extraction_dag():

    @task()
    def setup_schema_and_table() -> None:
        """Create bronze_enrichment.raw_plot_listing_extractions if missing."""
        import psycopg2
        from airflow.models import Variable

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()
            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze_enrichment")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bronze_enrichment.raw_plot_listing_extractions (
                    idempotency_hash                  TEXT PRIMARY KEY,
                    listing_id                        TEXT NOT NULL,
                    listing_url                       TEXT NOT NULL,
                    -- LLM extracted: numeric m²
                    implantation_area_m2              FLOAT,
                    construction_area_m2_above_ground FLOAT,
                    construction_area_m2_total        FLOAT,
                    area_loteamento_m2                FLOAT,
                    -- LLM extracted: counts
                    num_dwellings_allowed             INTEGER,
                    max_floors_allowed                INTEGER,
                    num_caves                         INTEGER,
                    -- LLM extracted: categorical
                    permit_status                     TEXT,
                    needs_loteamento                  BOOLEAN,
                    loteamento_complete               BOOLEAN,
                    -- Provenance
                    source_spans                      JSONB NOT NULL DEFAULT '{}'::jsonb,
                    -- DAG metadata
                    extraction_confidence             NUMERIC(4, 3),
                    extraction_status                 TEXT NOT NULL DEFAULT 'success',
                    error_message                     TEXT,
                    raw_response                      TEXT,
                    model_id                          TEXT NOT NULL,
                    input_tokens                      INTEGER,
                    output_tokens                     INTEGER,
                    cost_usd                          NUMERIC(8, 5),
                    extracted_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_plot_extr_listing_id "
                "ON bronze_enrichment.raw_plot_listing_extractions (listing_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_plot_extr_status "
                "ON bronze_enrichment.raw_plot_listing_extractions (extraction_status)"
            )
            conn.commit()
            log.info("[plot_extract] schema + table ready")
        finally:
            conn.close()

    @task()
    def extract_pending(_setup: None, dag_run=None) -> dict:
        """Main extraction loop. Sequential at v1 scope (~20 min for 403 rows).

        Reads pending listings from stg_plot_listings (those whose current
        sha256 hash is not yet in bronze_enrichment.raw_plot_listing_extractions).
        Calls Anthropic twice per listing (extract + self-eval), writes one
        row each. Aborts cleanly if cumulative cost passes max_cost_usd.
        """
        import hashlib
        import unicodedata

        import anthropic
        import psycopg2
        from airflow.models import Variable
        from psycopg2.extras import Json

        # Pydantic schema lives in the package — import here so the DAG file
        # remains importable even before the package is on PYTHONPATH.
        from pipelines.enrichment.plot_listing_extraction.schema import (
            PlotListingExtraction,
        )

        # ── DAG-run config ──
        conf = (dag_run.conf if dag_run and dag_run.conf else {}) or {}
        listing_id_filter: list[str] | None = conf.get("listing_ids")
        max_cost_usd: float = float(conf.get("max_cost_usd", DEFAULT_MAX_COST_USD))

        # ── Anthropic client ──
        # timeout=60s — Sonnet 4.6 occasionally hangs without an explicit
        # client-side cap. Observed 2026-05-29 mid-eval after row 13.
        api_key = Variable.get("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key, timeout=60.0)

        # Tool schema mirrors PlotListingExtraction. We force the model to
        # call this tool — guaranteed JSON-shaped response.
        tool_schema = {
            "name": "extract_plot_listing",
            "description": (
                "Record the structured plot-listing data extracted from the Portuguese description."
            ),
            "input_schema": PlotListingExtraction.model_json_schema(),
        }

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()

            # Build pending set: stg rows whose current hash is not in bronze.
            # We compute hash here (in SQL would require a sha256 extension);
            # cheaper to pull all stg + filter in Python.
            stg_filter_clauses = ["s.description IS NOT NULL"]
            stg_filter_params: list = []
            if listing_id_filter:
                stg_filter_clauses.append("s.listing_id = ANY(%s)")
                stg_filter_params.append(list(listing_id_filter))
            cur.execute(
                f"""
                SELECT s.listing_id, s.concelho_slug, s.description,
                       s.listing_url, s.lot_size, s.property_price
                FROM staging_dbt.stg_plot_listings s
                WHERE {" AND ".join(stg_filter_clauses)}
                ORDER BY s.concelho_slug, s.listing_id
                """,
                stg_filter_params,
            )
            stg_rows = cur.fetchall()
            log.info(
                "[plot_extract] %d stg rows in scope (filter=%s)",
                len(stg_rows),
                "all" if listing_id_filter is None else f"{len(listing_id_filter)} ids",
            )

            # Compute hashes; per-row check moved into the loop below to
            # avoid the double-spend race on concurrent triggers (senior-eng
            # review P0). We still pre-filter the obvious already-done set
            # here as a cheap optimization; the per-row guard is authoritative.
            def _hash(url: str, description: str) -> str:
                payload = (url + unicodedata.normalize("NFC", description).strip()).encode()
                return hashlib.sha256(payload).hexdigest()

            stg_with_hash = [
                (lid, concelho, desc, url, lot_size, price, _hash(url, desc))
                for (lid, concelho, desc, url, lot_size, price) in stg_rows
            ]

            # Pre-filter on hashes that are CURRENTLY in scope only — bounded
            # by the stg_rows we just fetched (vs scanning the whole bronze
            # table). Senior-eng review P1: keeps the read bounded as the
            # bronze table grows.
            in_scope_hashes = tuple(r[6] for r in stg_with_hash)
            if in_scope_hashes:
                cur.execute(
                    "SELECT idempotency_hash "
                    "FROM bronze_enrichment.raw_plot_listing_extractions "
                    "WHERE idempotency_hash = ANY(%s)",
                    (list(in_scope_hashes),),
                )
                already_done = {row[0] for row in cur.fetchall()}
            else:
                already_done = set()

            pending = [r for r in stg_with_hash if r[6] not in already_done]
            log.info(
                "[plot_extract] %d pending (skipping %d already done)",
                len(pending),
                len(stg_with_hash) - len(pending),
            )

            if not pending:
                return {
                    "pending": 0,
                    "extracted": 0,
                    "failed": 0,
                    "cost_usd": 0.0,
                    "stopped_for_cost": False,
                }

            insert_sql = """
                INSERT INTO bronze_enrichment.raw_plot_listing_extractions (
                    idempotency_hash, listing_id, listing_url,
                    implantation_area_m2, construction_area_m2_above_ground,
                    construction_area_m2_total, area_loteamento_m2,
                    num_dwellings_allowed, max_floors_allowed, num_caves,
                    permit_status, needs_loteamento, loteamento_complete,
                    source_spans,
                    extraction_confidence, extraction_status,
                    error_message, raw_response,
                    model_id, input_tokens, output_tokens, cost_usd
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (idempotency_hash) DO NOTHING
            """

            extracted = 0
            failed = 0
            cumulative_cost = 0.0
            stopped_for_cost = False

            def _reconnect():
                """Reopen warehouse connection after a transient OperationalError."""
                nonlocal conn, cur
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                conn = psycopg2.connect(
                    host=Variable.get("WAREHOUSE_HOST"),
                    port=int(Variable.get("WAREHOUSE_PORT")),
                    dbname=Variable.get("WAREHOUSE_DB"),
                    user=Variable.get("WAREHOUSE_USER"),
                    password=Variable.get("WAREHOUSE_PASSWORD"),
                )
                cur = conn.cursor()

            for lid, concelho, description, url, _lot_size, _price, hash_key in pending:
                if cumulative_cost >= max_cost_usd:
                    stopped_for_cost = True
                    break

                # Per-row idempotency check — guards against the race where
                # a second manual trigger lands mid-run (P0 from senior-eng
                # review). Cheap (PK lookup); skips the $0.015 LLM call.
                try:
                    cur.execute(
                        "SELECT 1 FROM bronze_enrichment.raw_plot_listing_extractions "
                        "WHERE idempotency_hash = %s",
                        (hash_key,),
                    )
                    if cur.fetchone() is not None:
                        log.info(
                            "[plot_extract] %s already extracted by concurrent run — skipping", lid
                        )
                        continue
                except psycopg2.OperationalError as exc:
                    log.warning(
                        "[plot_extract] db OperationalError on lookup, reconnecting: %s", exc
                    )
                    _reconnect()
                    cur.execute(
                        "SELECT 1 FROM bronze_enrichment.raw_plot_listing_extractions "
                        "WHERE idempotency_hash = %s",
                        (hash_key,),
                    )
                    if cur.fetchone() is not None:
                        continue

                log.info("[plot_extract] extracting %s (%s) …", lid, concelho)
                result = _extract_one(
                    client=client,
                    description=description,
                    tool_schema=tool_schema,
                )

                cumulative_cost += result["cost_usd"]
                row_values = (
                    hash_key,
                    lid,
                    url,
                    result["fields"].get("implantation_area_m2"),
                    result["fields"].get("construction_area_m2_above_ground"),
                    result["fields"].get("construction_area_m2_total"),
                    result["fields"].get("area_loteamento_m2"),
                    result["fields"].get("num_dwellings_allowed"),
                    result["fields"].get("max_floors_allowed"),
                    result["fields"].get("num_caves"),
                    result["fields"].get("permit_status"),
                    result["fields"].get("needs_loteamento"),
                    result["fields"].get("loteamento_complete"),
                    Json(result["fields"].get("source_spans") or {}),
                    result["confidence"],
                    result["status"],
                    result["error_message"],
                    result["raw_response"],
                    ANTHROPIC_MODEL,
                    result["input_tokens"],
                    result["output_tokens"],
                    result["cost_usd"],
                )
                try:
                    cur.execute(insert_sql, row_values)
                    conn.commit()
                except psycopg2.OperationalError as exc:
                    log.warning(
                        "[plot_extract] db OperationalError on insert, reconnecting + retrying: %s",
                        exc,
                    )
                    _reconnect()
                    cur.execute(insert_sql, row_values)
                    conn.commit()

                if result["status"] == "success":
                    extracted += 1
                else:
                    failed += 1
                if (extracted + failed) % 25 == 0:
                    log.info(
                        "[plot_extract] progress: %d ok, %d failed, $%.3f cumulative",
                        extracted,
                        failed,
                        cumulative_cost,
                    )

            cur.close()

            stats = {
                "pending": len(pending),
                "extracted": extracted,
                "failed": failed,
                "cost_usd": round(cumulative_cost, 4),
                "stopped_for_cost": stopped_for_cost,
                "max_cost_usd": max_cost_usd,
            }
            log.info("[plot_extract] done: %s", stats)
            # Cost-ceiling overshoot is a partial backfill — fail loud so
            # oncall doesn't see green. Senior-eng review P0.
            if stopped_for_cost:
                raise RuntimeError(
                    f"cost ceiling ${max_cost_usd:.2f} reached after "
                    f"{extracted} ok / {failed} failed (${cumulative_cost:.3f} spent); "
                    f"{len(pending) - extracted - failed} rows still pending. "
                    f"Re-trigger after either raising max_cost_usd or reducing scope."
                )
            return stats
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @task()
    def report_coverage(stats: dict) -> dict:
        """Surface overall extraction coverage post-run."""
        import psycopg2
        from airflow.models import Variable

        conn = psycopg2.connect(
            host=Variable.get("WAREHOUSE_HOST"),
            port=int(Variable.get("WAREHOUSE_PORT")),
            dbname=Variable.get("WAREHOUSE_DB"),
            user=Variable.get("WAREHOUSE_USER"),
            password=Variable.get("WAREHOUSE_PASSWORD"),
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE extraction_status='success') AS success,
                    COUNT(*) FILTER (WHERE extraction_status='failed') AS failed,
                    AVG(extraction_confidence) FILTER (WHERE extraction_status='success') AS avg_conf,
                    COALESCE(SUM(cost_usd), 0) AS lifetime_cost
                FROM bronze_enrichment.raw_plot_listing_extractions
                """
            )
            total, success, failed, avg_conf, lifetime_cost = cur.fetchone()
        finally:
            conn.close()

        coverage = {
            "this_run": stats,
            "lifetime": {
                "total_rows": total,
                "success": success,
                "failed": failed,
                "avg_confidence": float(avg_conf) if avg_conf is not None else None,
                "lifetime_cost_usd": round(float(lifetime_cost), 4),
            },
        }
        log.info("[plot_extract] coverage: %s", coverage)
        return coverage

    setup = setup_schema_and_table()
    run_stats = extract_pending(setup)
    report_coverage(run_stats)


# ────────────────────────────────────────────────────────────────────────
# Per-listing helper (module-level so it can be unit-tested without Airflow)
# ────────────────────────────────────────────────────────────────────────


def _extract_one(client, description: str, tool_schema: dict) -> dict:
    """Run one extraction + self-eval cycle for a single listing.

    Returns a dict with: fields, confidence, status, error_message,
    raw_response, input_tokens, output_tokens, cost_usd.

    Wraps the API call in EXTRACTION_RETRIES of exponential back-off.
    On final failure, returns a sentinel result with status='failed'.
    """
    import json
    import time

    import anthropic

    from pipelines.enrichment.plot_listing_extraction.schema import (
        PlotListingExtraction,
    )

    last_exc: Exception | None = None
    extract_response = None

    # Retry on the full set of transient Anthropic errors. RateLimitError +
    # APITimeoutError do NOT subclass APIError in some SDK versions, so list
    # them explicitly (senior-eng review P1).
    retryable_errors = (
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
        anthropic.APIError,  # broad catch-all last
    )
    for attempt in range(EXTRACTION_RETRIES):
        try:
            extract_response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=2048,
                system=EXTRACTION_SYSTEM_PROMPT,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": "extract_plot_listing"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Extract structured data from this Portuguese plot "
                            "listing description by calling the extract_plot_listing "
                            "tool:\n\n"
                            f"{description}"
                        ),
                    }
                ],
            )
            break
        except retryable_errors as exc:
            last_exc = exc
            if attempt < EXTRACTION_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue

    if extract_response is None:
        # All retries failed.
        return _failed_result(
            error=f"anthropic API failed after {EXTRACTION_RETRIES} retries: {last_exc!r}",
            raw_response=None,
            input_tokens=0,
            output_tokens=0,
        )

    # Pull the tool_use block; if missing or malformed, sentinel-row.
    tool_input: dict | None = None
    raw_dump = str(extract_response.content)
    for block in extract_response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "extract_plot_listing"
        ):
            tool_input = block.input
            break

    if tool_input is None:
        return _failed_result(
            error="anthropic returned no extract_plot_listing tool_use block",
            raw_response=raw_dump[:4000],
            input_tokens=extract_response.usage.input_tokens,
            output_tokens=extract_response.usage.output_tokens,
        )

    # Defensive: source_spans must be a dict. Some models serialize it as a
    # JSON-formatted string instead — try to recover by parsing, else default
    # to {}. Caught 1/50 cases in the Haiku eval run on 2026-05-29.
    if isinstance(tool_input.get("source_spans"), str):
        try:
            tool_input["source_spans"] = json.loads(tool_input["source_spans"])
        except (json.JSONDecodeError, TypeError):
            tool_input["source_spans"] = {}

    # Validate against Pydantic (extra='forbid' catches schema drift).
    try:
        extraction = PlotListingExtraction(**tool_input)
    except Exception as exc:
        return _failed_result(
            error=f"pydantic validation failed: {exc!r}",
            raw_response=json.dumps(tool_input, ensure_ascii=False)[:4000],
            input_tokens=extract_response.usage.input_tokens,
            output_tokens=extract_response.usage.output_tokens,
        )

    # Self-eval second call was dropped 2026-05-30 after the 50-row eval
    # baseline showed zero correlation between self-rated confidence and
    # actual field-correctness (conf >= 0.7 → 88.4% correct; conf < 0.7 →
    # 88.9% correct). The call doubled cost for no signal. extraction_confidence
    # column kept as nullable for future re-introduction if a calibrated
    # signal becomes available.
    total_in = extract_response.usage.input_tokens
    total_out = extract_response.usage.output_tokens
    cost_usd = round(
        (total_in / 1_000_000) * PRICE_INPUT_PER_MTOK
        + (total_out / 1_000_000) * PRICE_OUTPUT_PER_MTOK,
        5,
    )

    return {
        "fields": extraction.model_dump(),
        "confidence": None,
        "status": "success",
        "error_message": None,
        "raw_response": None,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cost_usd": cost_usd,
    }


def _failed_result(
    *,
    error: str,
    raw_response: str | None,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    """Build a sentinel-row result with all fields nulled out."""
    cost_usd = round(
        (input_tokens / 1_000_000) * PRICE_INPUT_PER_MTOK
        + (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MTOK,
        5,
    )
    return {
        "fields": {
            "implantation_area_m2": None,
            "construction_area_m2_above_ground": None,
            "construction_area_m2_total": None,
            "area_loteamento_m2": None,
            "num_dwellings_allowed": None,
            "max_floors_allowed": None,
            "num_caves": None,
            "permit_status": None,
            "needs_loteamento": None,
            "loteamento_complete": None,
            "source_spans": {},
        },
        "confidence": None,
        "status": "failed",
        "error_message": error[:2000],
        "raw_response": raw_response,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }


dag = plot_listing_extraction_dag()
