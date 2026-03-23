"""
Image Classification — Claude Vision Pipeline

Classifies Idealista listing images using Claude Vision API.
Two sequential task groups:
  A) Image classification: render detection, condition assessment, finish quality
  B) Floor plan extraction: room-level areas from plan images

Design decisions (from senior dev review):
  - 1 row per property_id in image_classifications (not per-image)
  - UNIQUE constraint on property_id + ON CONFLICT DO UPDATE
  - prompt_version column enables re-classification after prompt changes
  - tenacity retries on API calls (not just Airflow task-level)
  - Batch DB writes via execute_batch
  - DAG chain: bronze_load → image_classification → dbt_build
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

log = logging.getLogger(__name__)

# ── Prompt versioning ────────────────────────────────────────────────────────
# Bump this when you change the prompts below. The dedup query will
# automatically re-classify listings classified with older versions.
CURRENT_PROMPT_VERSION = 1

# ── Geographic scope ─────────────────────────────────────────────────────────
# Filter to specific concelhos. Set to None or empty list to classify all.
# Expand this list as you scale to more municipalities.
TARGET_CONCELHOS = ["aveiro"]

# ── Claude Vision prompts ────────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """\
You are a real estate image analyst. Analyze these property listing images and return a single JSON object with exactly these fields:

{
  "is_render": true/false,
  "render_confidence": 0.0-1.0,
  "condition_label": "needs_renovation" | "habitable" | "renovated",
  "condition_confidence": 0.0-1.0,
  "finish_quality": "basic" | "standard" | "premium",
  "finish_quality_confidence": 0.0-1.0
}

Definitions:
- is_render: TRUE if the image is a 3D render/CGI (not a real photograph). Renders have perfect lighting, no imperfections, unnaturally clean surfaces.
- condition_label:
  - needs_renovation: any level of renovation needed — from cosmetic updates (dated tiles, yellowed walls, worn floors) to full structural work (exposed wiring, crumbling plaster, water damage)
  - habitable: functional and livable as-is — clean, maintained, no visible damage, but not recently updated
  - renovated: clearly new or recently updated materials — fresh paint, modern fixtures, new appliances, contemporary finishes
- finish_quality:
  - basic: laminate/vinyl floors, basic white tiles, no-name appliances, plastic fixtures, cheap materials
  - standard: ceramic tile/laminate, standard kitchen, functional bathroom, decent but unremarkable finishes
  - premium: hardwood/marble floors, quality kitchen (stone counters, branded appliances), modern bathroom, designer fixtures, high-end materials

Return ONLY a single JSON object, no other text. Do NOT return an array."""

FLOOR_PLAN_PROMPT = """\
You are a real estate floor plan analyst. Extract structured data from this floor plan image.

Return a JSON object with exactly these fields:
{
  "typology": "T0" | "T1" | "T2" | "T3" | "T4" | "T5+",
  "floor_label": "Piso 1" | "RC" | "Cave" | etc. or null if not visible,
  "total_area_m2": number or null if not labeled,
  "rooms": {"room_name": area_m2, ...} or {} if areas not labeled,
  "num_bedrooms": integer,
  "num_bathrooms": integer,
  "has_terrace": true/false,
  "terrace_area_m2": number or null,
  "extraction_confidence": 0.0-1.0
}

For the rooms object, use these canonical Portuguese room names as keys:
  suite, quarto, sala, cozinha, wc, hall, varanda, escritorio, arrumos, garagem
Append _1, _2 etc. for duplicates (e.g. quarto_1, quarto_2, wc_1, wc_2).
Only include rooms where the area in m² is clearly labeled on the plan.

If this image is NOT a floor plan (e.g. it's a 3D render, elevation, garage plan, or site map), return null.

Return ONLY the JSON object (or null), no other text."""


# ── Required response keys ───────────────────────────────────────────────────
CLASSIFICATION_REQUIRED_KEYS = {"is_render", "condition_label", "finish_quality"}


# ── Helper functions ─────────────────────────────────────────────────────────


def _get_warehouse_conn():
    """Create a psycopg2 connection to the warehouse using Airflow Variables."""
    import psycopg2
    from airflow.models import Variable

    return psycopg2.connect(
        host=Variable.get("WAREHOUSE_HOST"),
        port=int(Variable.get("WAREHOUSE_PORT")),
        dbname=Variable.get("WAREHOUSE_DB"),
        user=Variable.get("WAREHOUSE_USER"),
        password=Variable.get("WAREHOUSE_PASSWORD"),
    )


def _select_images_by_tag(
    property_images: list[str], property_image_tags: list[str]
) -> list[dict]:
    """Pick the 3 most informative images using tag-based selection.

    Priority:
      Image 1: kitchen or bathroom (best for finish quality + condition)
      Image 2: facade (best for render detection + exterior condition)
      Image 3: livingRoom or bedroom (secondary interior for broader view)
      Fallback: fill remaining slots with next available images
    """
    if not property_images or not property_image_tags:
        return []

    # Build tag→positions index
    tagged: dict[str, list[int]] = {}
    for i, tag in enumerate(property_image_tags):
        tagged.setdefault(tag, []).append(i)

    selected = []
    used_positions: set[int] = set()

    def _pick(tag_priority: list[str]) -> bool:
        for tag in tag_priority:
            if tag in tagged:
                for pos in tagged[tag]:
                    if pos not in used_positions and pos < len(property_images):
                        selected.append({
                            "url": property_images[pos],
                            "position": pos,
                            "tag": tag,
                        })
                        used_positions.add(pos)
                        return True
        return False

    # Image 1: interior
    _pick(["kitchen", "bathroom"])

    # Image 2: facade
    _pick(["facade"])

    # Image 3: secondary interior
    _pick(["livingRoom", "bedroom"])

    # Fallback: fill remaining slots up to 3 with any available images
    for i in range(len(property_images)):
        if len(selected) >= 3:
            break
        if i not in used_positions:
            tag = property_image_tags[i] if i < len(property_image_tags) else "unknown"
            selected.append({"url": property_images[i], "position": i, "tag": tag})
            used_positions.add(i)

    return selected[:3]


def _select_plan_images(
    property_images: list[str], property_image_tags: list[str]
) -> list[dict]:
    """Select all images tagged 'plan' for floor plan extraction."""
    if not property_images or not property_image_tags:
        return []

    plans = []
    for i, tag in enumerate(property_image_tags):
        if tag == "plan" and i < len(property_images):
            plans.append({
                "url": property_images[i],
                "position": i,
                "tag": "plan",
            })
    return plans


def _call_claude_vision(client, model: str, prompt: str, image_urls: list[str]):
    """Call Claude Vision API with image URLs. Returns parsed JSON or None.

    Uses tenacity for retries on rate limits and server errors.
    """
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    import anthropic

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(
            (anthropic.RateLimitError, anthropic.APIStatusError)
        ),
    )
    def _api_call():
        content = []
        for url in image_urls:
            content.append({
                "type": "image",
                "source": {"type": "url", "url": url},
            })
        content.append({"type": "text", "text": prompt})

        return client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

    try:
        response = _api_call()
        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        if raw_text.lower() == "null":
            return None
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        log.warning("[cv] JSON parse error: %s — raw: %.200s", exc, raw_text)
        return None
    except Exception as exc:
        log.warning("[cv] Claude Vision call failed after retries: %s", exc)
        return None


# ── DAG definition ───────────────────────────────────────────────────────────


def _on_failure(context):
    """DAG-level failure callback for alerting."""
    dag_id = context.get("dag", {}).dag_id if context.get("dag") else "unknown"
    task_id = context.get("task_instance", {}).task_id if context.get("task_instance") else "unknown"
    log.error("[cv] FAILURE in %s.%s: %s", dag_id, task_id, context.get("exception"))


def _create_dag():
    from airflow.decorators import dag, task

    default_args = {
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        "on_failure_callback": _on_failure,
    }

    @dag(
        dag_id="image_classification",
        description=(
            "Claude Vision image classification + floor plan extraction. "
            "Classifies new listings only (dedup on property_id + prompt_version)."
        ),
        schedule=None,
        start_date=None,
        catchup=False,
        max_active_runs=1,
        default_args=default_args,
        tags=["idealista", "cv", "classification", "images"],
    )
    def image_classification():

        # ── Task: Create tables ──────────────────────────────────────────

        @task()
        def create_tables() -> None:
            """Create image_classifications and floor_plan_extractions tables."""
            conn = _get_warehouse_conn()
            try:
                conn.autocommit = True
                cur = conn.cursor()

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bronze_listings.image_classifications (
                        id                        BIGSERIAL PRIMARY KEY,
                        property_id               VARCHAR(50) NOT NULL UNIQUE,
                        image_urls                TEXT[],
                        image_tags                TEXT[],
                        is_render                 BOOLEAN,
                        render_confidence         NUMERIC(4,3),
                        condition_label           VARCHAR(30),
                        condition_confidence      NUMERIC(4,3),
                        finish_quality            VARCHAR(20),
                        finish_quality_confidence NUMERIC(4,3),
                        raw_response              JSONB,
                        model_used                VARCHAR(50),
                        prompt_version            SMALLINT DEFAULT 1,
                        _classified_at            TIMESTAMPTZ DEFAULT NOW(),
                        _batch_id                 VARCHAR(50)
                    )
                """)

                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_ic_classified_at ON bronze_listings.image_classifications(_classified_at)",
                    "CREATE INDEX IF NOT EXISTS idx_ic_batch_id ON bronze_listings.image_classifications(_batch_id)",
                ]:
                    cur.execute(idx_sql)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bronze_listings.floor_plan_extractions (
                        id                        BIGSERIAL PRIMARY KEY,
                        property_id               VARCHAR(50) NOT NULL,
                        image_url                 TEXT NOT NULL,
                        image_position            SMALLINT,
                        typology                  VARCHAR(10),
                        floor_label               VARCHAR(50),
                        total_area_m2             NUMERIC(8,2),
                        rooms                     JSONB,
                        num_bedrooms              SMALLINT,
                        num_bathrooms             SMALLINT,
                        has_terrace               BOOLEAN,
                        terrace_area_m2           NUMERIC(8,2),
                        extraction_confidence     NUMERIC(4,3),
                        raw_response              JSONB,
                        model_used                VARCHAR(50),
                        prompt_version            SMALLINT DEFAULT 1,
                        _extracted_at             TIMESTAMPTZ DEFAULT NOW(),
                        _batch_id                 VARCHAR(50)
                    )
                """)

                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_fp_property_id ON bronze_listings.floor_plan_extractions(property_id)",
                    "CREATE INDEX IF NOT EXISTS idx_fp_extracted_at ON bronze_listings.floor_plan_extractions(_extracted_at)",
                    "CREATE INDEX IF NOT EXISTS idx_fp_batch_id ON bronze_listings.floor_plan_extractions(_batch_id)",
                ]:
                    cur.execute(idx_sql)

                log.info("[cv] Ensured image_classifications and floor_plan_extractions tables exist")
                cur.close()
            finally:
                conn.close()

        # ── Task Group A: Image Classification ───────────────────────────

        @task()
        def fetch_unclassified_listings() -> list[dict]:
            """Fetch property_ids not yet classified (or classified with older prompt)."""
            conn = _get_warehouse_conn()
            try:
                cur = conn.cursor()

                # Build optional concelho filter
                concelho_clause = ""
                params: list = []
                if TARGET_CONCELHOS:
                    placeholders = ",".join(["%s"] * len(TARGET_CONCELHOS))
                    concelho_clause = f"AND _concelho IN ({placeholders})"
                    params.extend(TARGET_CONCELHOS)
                params.append(CURRENT_PROMPT_VERSION)

                cur.execute(
                    f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (property_id)
                            property_id,
                            property_images,
                            property_image_tags
                        FROM bronze_listings.raw_idealista
                        WHERE property_id IS NOT NULL
                          AND property_images IS NOT NULL
                          AND jsonb_array_length(property_images) > 0
                          {concelho_clause}
                        ORDER BY property_id, _scrape_date DESC
                    )
                    SELECT l.property_id, l.property_images, l.property_image_tags
                    FROM latest l
                    LEFT JOIN bronze_listings.image_classifications ic
                        ON l.property_id = ic.property_id
                    WHERE ic.property_id IS NULL
                       OR ic.prompt_version < %s
                    ORDER BY l.property_id
                    """,
                    params,
                )

                rows = cur.fetchall()
                cur.close()
            finally:
                conn.close()

            listings = []
            for property_id, images_json, tags_json in rows:
                images = images_json if isinstance(images_json, list) else json.loads(images_json) if images_json else []
                tags = tags_json if isinstance(tags_json, list) else json.loads(tags_json) if tags_json else []
                if images:
                    listings.append({
                        "property_id": property_id,
                        "images": images,
                        "tags": tags,
                    })

            log.info("[cv] Found %d unclassified listings (prompt_version < %d)", len(listings), CURRENT_PROMPT_VERSION)
            return listings

        @task()
        def classify_images(listings: list[dict]) -> dict:
            """Classify images using Claude Vision API with batch writes."""
            import time

            import anthropic
            import psycopg2.extras
            from airflow.models import Variable

            if not listings:
                log.info("[cv] No listings to classify")
                return {"classified": 0, "errors": 0}

            client = anthropic.Anthropic(api_key=Variable.get("ANTHROPIC_API_KEY"))
            model = Variable.get("CV_MODEL", default_var="claude-sonnet-4-20250514")
            batch_id = __import__("datetime").datetime.now().strftime("%Y%m%dT%H%M%S")

            conn = _get_warehouse_conn()
            try:
                cur = conn.cursor()

                insert_sql = """
                    INSERT INTO bronze_listings.image_classifications (
                        property_id, image_urls, image_tags,
                        is_render, render_confidence,
                        condition_label, condition_confidence,
                        finish_quality, finish_quality_confidence,
                        raw_response, model_used, prompt_version, _batch_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (property_id) DO UPDATE SET
                        image_urls = EXCLUDED.image_urls,
                        image_tags = EXCLUDED.image_tags,
                        is_render = EXCLUDED.is_render,
                        render_confidence = EXCLUDED.render_confidence,
                        condition_label = EXCLUDED.condition_label,
                        condition_confidence = EXCLUDED.condition_confidence,
                        finish_quality = EXCLUDED.finish_quality,
                        finish_quality_confidence = EXCLUDED.finish_quality_confidence,
                        raw_response = EXCLUDED.raw_response,
                        model_used = EXCLUDED.model_used,
                        prompt_version = EXCLUDED.prompt_version,
                        _classified_at = NOW(),
                        _batch_id = EXCLUDED._batch_id
                """

                classified = 0
                errors = 0
                batch_rows = []

                for i, listing in enumerate(listings):
                    property_id = listing["property_id"]
                    images = listing["images"]
                    tags = listing["tags"]

                    # Tag-based image selection (3 images)
                    selected = _select_images_by_tag(images, tags)
                    if not selected:
                        log.warning("[cv] %s: no images selected, skipping", property_id)
                        errors += 1
                        continue

                    image_urls = [img["url"] for img in selected]
                    image_tags = [img["tag"] for img in selected]

                    result = _call_claude_vision(
                        client, model, CLASSIFICATION_PROMPT, image_urls
                    )

                    if result is None:
                        errors += 1
                        log.warning("[cv] %s: Claude Vision returned None", property_id)
                        continue

                    # Validate required keys
                    if not CLASSIFICATION_REQUIRED_KEYS.issubset(result.keys()):
                        errors += 1
                        log.warning(
                            "[cv] %s: incomplete response, missing keys: %s",
                            property_id,
                            CLASSIFICATION_REQUIRED_KEYS - result.keys(),
                        )
                        continue

                    batch_rows.append((
                        property_id,
                        image_urls,
                        image_tags,
                        result.get("is_render"),
                        result.get("render_confidence"),
                        result.get("condition_label"),
                        result.get("condition_confidence"),
                        result.get("finish_quality"),
                        result.get("finish_quality_confidence"),
                        json.dumps(result, ensure_ascii=False),
                        model,
                        CURRENT_PROMPT_VERSION,
                        batch_id,
                    ))

                    classified += 1

                    # Batch write every 100 listings
                    if len(batch_rows) >= 100:
                        psycopg2.extras.execute_batch(cur, insert_sql, batch_rows, page_size=100)
                        conn.commit()
                        batch_rows = []

                    # Progress logging every 50
                    if (i + 1) % 50 == 0:
                        est_cost = classified * 0.019
                        log.info(
                            "[cv] Progress: %d/%d classified, %d errors, ~$%.2f estimated",
                            classified, len(listings), errors, est_cost,
                        )

                    # Rate limiting — 1.5s avoids excessive 429 retries on free/low tier
                    time.sleep(1.5)

                # Flush remaining rows
                if batch_rows:
                    psycopg2.extras.execute_batch(cur, insert_sql, batch_rows, page_size=100)
                    conn.commit()

                cur.close()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            est_cost = classified * 0.019
            log.info(
                "[cv] Classification done: %d classified, %d errors, ~$%.2f estimated cost",
                classified, errors, est_cost,
            )
            return {"classified": classified, "errors": errors, "estimated_cost_usd": round(est_cost, 2)}

        # ── Task Group B: Floor Plan Extraction ──────────────────────────

        @task()
        def fetch_unextracted_plans() -> list[dict]:
            """Fetch property_ids with plan images not yet extracted (or older prompt)."""
            conn = _get_warehouse_conn()
            try:
                cur = conn.cursor()

                # Build optional concelho filter
                concelho_clause = ""
                params: list = []
                if TARGET_CONCELHOS:
                    placeholders = ",".join(["%s"] * len(TARGET_CONCELHOS))
                    concelho_clause = f"AND _concelho IN ({placeholders})"
                    params.extend(TARGET_CONCELHOS)
                params.append(CURRENT_PROMPT_VERSION)

                cur.execute(
                    f"""
                    WITH latest AS (
                        SELECT DISTINCT ON (property_id)
                            property_id,
                            property_images,
                            property_image_tags
                        FROM bronze_listings.raw_idealista
                        WHERE property_id IS NOT NULL
                          AND property_images IS NOT NULL
                          AND property_image_tags IS NOT NULL
                          AND property_image_tags::TEXT LIKE '%%"plan"%%'
                          {concelho_clause}
                        ORDER BY property_id, _scrape_date DESC
                    )
                    SELECT l.property_id, l.property_images, l.property_image_tags
                    FROM latest l
                    LEFT JOIN (
                        SELECT DISTINCT property_id
                        FROM bronze_listings.floor_plan_extractions
                        WHERE prompt_version >= %s
                    ) fp ON l.property_id = fp.property_id
                    WHERE fp.property_id IS NULL
                    ORDER BY l.property_id
                    """,
                    params,
                )

                rows = cur.fetchall()
                cur.close()
            finally:
                conn.close()

            listings = []
            for property_id, images_json, tags_json in rows:
                images = images_json if isinstance(images_json, list) else json.loads(images_json) if images_json else []
                tags = tags_json if isinstance(tags_json, list) else json.loads(tags_json) if tags_json else []
                plans = _select_plan_images(images, tags)
                if plans:
                    listings.append({
                        "property_id": property_id,
                        "plans": plans,
                    })

            log.info("[cv] Found %d listings with unextracted floor plans", len(listings))
            return listings

        @task()
        def extract_floor_plans(listings: list[dict]) -> dict:
            """Extract room-level data from floor plan images via Claude Vision."""
            import time

            import anthropic
            import psycopg2.extras
            from airflow.models import Variable

            if not listings:
                log.info("[cv] No floor plans to extract")
                return {"extracted": 0, "errors": 0, "null_plans": 0}

            client = anthropic.Anthropic(api_key=Variable.get("ANTHROPIC_API_KEY"))
            model = Variable.get("CV_MODEL", default_var="claude-sonnet-4-20250514")
            batch_id = __import__("datetime").datetime.now().strftime("%Y%m%dT%H%M%S")

            conn = _get_warehouse_conn()
            try:
                cur = conn.cursor()

                # Delete old-version extractions for listings we're about to re-process
                property_ids = [l["property_id"] for l in listings]
                if property_ids:
                    cur.execute(
                        """
                        DELETE FROM bronze_listings.floor_plan_extractions
                        WHERE property_id = ANY(%s) AND prompt_version < %s
                        """,
                        (property_ids, CURRENT_PROMPT_VERSION),
                    )
                    conn.commit()

                insert_sql = """
                    INSERT INTO bronze_listings.floor_plan_extractions (
                        property_id, image_url, image_position,
                        typology, floor_label, total_area_m2, rooms,
                        num_bedrooms, num_bathrooms,
                        has_terrace, terrace_area_m2,
                        extraction_confidence,
                        raw_response, model_used, prompt_version, _batch_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                extracted = 0
                errors = 0
                null_plans = 0
                batch_rows = []

                for listing in listings:
                    property_id = listing["property_id"]

                    for plan_img in listing["plans"]:
                        result = _call_claude_vision(
                            client, model, FLOOR_PLAN_PROMPT, [plan_img["url"]]
                        )

                        if result is None:
                            null_plans += 1
                            continue

                        batch_rows.append((
                            property_id,
                            plan_img["url"],
                            plan_img["position"],
                            result.get("typology"),
                            result.get("floor_label"),
                            result.get("total_area_m2"),
                            json.dumps(result.get("rooms", {}), ensure_ascii=False),
                            result.get("num_bedrooms"),
                            result.get("num_bathrooms"),
                            result.get("has_terrace"),
                            result.get("terrace_area_m2"),
                            result.get("extraction_confidence"),
                            json.dumps(result, ensure_ascii=False),
                            model,
                            CURRENT_PROMPT_VERSION,
                            batch_id,
                        ))
                        extracted += 1

                        # Batch write every 100 rows
                        if len(batch_rows) >= 100:
                            psycopg2.extras.execute_batch(cur, insert_sql, batch_rows, page_size=100)
                            conn.commit()
                            batch_rows = []

                        if extracted % 50 == 0:
                            log.info(
                                "[cv] Floor plan progress: %d extracted, %d null, %d errors",
                                extracted, null_plans, errors,
                            )

                        time.sleep(0.1)

                # Flush remaining
                if batch_rows:
                    psycopg2.extras.execute_batch(cur, insert_sql, batch_rows, page_size=100)
                    conn.commit()

                cur.close()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            log.info(
                "[cv] Floor plan extraction done: %d extracted, %d null, %d errors",
                extracted, null_plans, errors,
            )
            return {"extracted": extracted, "errors": errors, "null_plans": null_plans}

        # ── Task wiring (sequential: classification → floor plans) ───────

        tables_ready = create_tables()

        # Group A: Image classification
        unclassified = fetch_unclassified_listings()
        tables_ready >> unclassified
        classification_result = classify_images(unclassified)

        # Group B: Floor plan extraction (runs after classification)
        unextracted = fetch_unextracted_plans()
        classification_result >> unextracted
        extraction_result = extract_floor_plans(unextracted)

        # Trigger dbt build after both groups complete
        from airflow.operators.trigger_dagrun import TriggerDagRunOperator

        trigger_dbt = TriggerDagRunOperator(
            task_id="trigger_dbt_pipeline",
            trigger_dag_id="dbt_idealista_build",
            wait_for_completion=True,
            reset_dag_run=True,
            poke_interval=10,
        )
        extraction_result >> trigger_dbt

    return image_classification()


dag = _create_dag()
