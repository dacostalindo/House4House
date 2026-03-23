"""
Phase 0 — 30-Image Model Comparison (Haiku vs Sonnet)

Stratified sample: 10 good + 10 newdevelopment + 10 renew.
Uses the actual 3-image tag-based selection from the DAG.
Compares Haiku vs Sonnet on the same images.
Outputs results to scripts/phase0_results.json + prints summary table.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import anthropic

# ── Load .env ────────────────────────────────────────────────────────────────
env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODELS = [
    ("haiku", "claude-haiku-4-5-20251001"),
    ("sonnet", "claude-sonnet-4-20250514"),
]

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
  - needs_renovation: any level of renovation needed — from cosmetic updates to full structural work
  - habitable: functional and livable as-is — clean, maintained, no visible damage, but not recently updated
  - renovated: clearly new or recently updated materials — fresh paint, modern fixtures, new appliances
- finish_quality:
  - basic: laminate/vinyl floors, basic white tiles, no-name appliances, cheap materials
  - standard: ceramic tile/laminate, standard kitchen, functional bathroom, decent but unremarkable
  - premium: hardwood/marble floors, quality kitchen (stone counters, branded appliances), modern bathroom, designer fixtures

Return ONLY a single JSON object, no other text. Do NOT return an array."""


# ── Tag-based image selection (mirrors DAG logic) ────────────────────────────

def select_images_by_tag(images: list[str], tags: list[str]) -> list[dict]:
    """Pick 3 most informative images by tag. Mirrors _select_images_by_tag in the DAG."""
    if not images or not tags:
        return []

    tagged: dict[str, list[int]] = {}
    for i, tag in enumerate(tags):
        tagged.setdefault(tag, []).append(i)

    selected = []
    used: set[int] = set()

    def pick(priorities: list[str]) -> bool:
        for tag in priorities:
            if tag in tagged:
                for pos in tagged[tag]:
                    if pos not in used and pos < len(images):
                        selected.append({"url": images[pos], "position": pos, "tag": tag})
                        used.add(pos)
                        return True
        return False

    pick(["kitchen", "bathroom"])
    pick(["facade"])
    pick(["livingRoom", "bedroom"])

    for i in range(len(images)):
        if len(selected) >= 3:
            break
        if i not in used:
            tag = tags[i] if i < len(tags) else "unknown"
            selected.append({"url": images[i], "position": i, "tag": tag})
            used.add(i)

    return selected[:3]


# ── Claude Vision call ───────────────────────────────────────────────────────

def call_vision(model_id: str, image_urls: list[str]) -> dict:
    """Call Claude Vision with multiple image URLs."""
    try:
        content = []
        for url in image_urls:
            content.append({"type": "image", "source": {"type": "url", "url": url}})
        content.append({"type": "text", "text": CLASSIFICATION_PROMPT})

        response = client.messages.create(
            model=model_id,
            max_tokens=512,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        parsed = json.loads(raw)
        # Claude sometimes returns a list wrapping the dict
        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            return {"success": False, "error": f"Unexpected response type: {type(parsed).__name__}"}
        return {
            "success": True,
            "result": parsed,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── Fetch 30 listings from warehouse ─────────────────────────────────────────

def fetch_sample_listings() -> list[dict]:
    """Query 30 stratified listings (10 per condition) via docker exec."""
    sql = """
    WITH deduped AS (
        SELECT DISTINCT ON (property_id)
            property_id,
            property_url,
            property_images::TEXT AS images_text,
            property_image_tags::TEXT AS tags_text,
            property_condition
        FROM bronze_listings.raw_idealista
        WHERE property_images IS NOT NULL
          AND jsonb_array_length(property_images) > 3
          AND property_image_tags IS NOT NULL
        ORDER BY property_id, _scrape_date DESC
    ),
    ranked AS (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY property_condition ORDER BY RANDOM()) AS rn
        FROM deduped
    )
    SELECT property_id, property_url, property_condition, images_text, tags_text
    FROM ranked
    WHERE rn <= 10
    ORDER BY property_condition, rn;
    """

    result = subprocess.run(
        ["docker", "exec", "house4house-warehouse-1",
         "psql", "-U", "warehouse", "-d", "house4house",
         "-t", "-A", "-F", "|||", "-c", sql],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"DB query failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    listings = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|||")
        if len(parts) < 5:
            continue
        pid, url, condition, images_str, tags_str = parts[0], parts[1], parts[2], parts[3], parts[4]
        images = json.loads(images_str)
        tags = json.loads(tags_str)
        listings.append({
            "property_id": pid,
            "listing_url": url,
            "condition": condition,
            "images": images,
            "tags": tags,
        })

    return listings


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Fetching 30 stratified listings from warehouse...")
    listings = fetch_sample_listings()
    print(f"Got {len(listings)} listings: {', '.join(f'{c}: {sum(1 for l in listings if l["condition"]==c)}' for c in ['good','newdevelopment','renew'])}")

    results = []
    total_cost = {"haiku": 0.0, "sonnet": 0.0}

    for i, listing in enumerate(listings):
        pid = listing["property_id"]
        selected = select_images_by_tag(listing["images"], listing["tags"])
        image_urls = [s["url"] for s in selected]
        image_tags = [s["tag"] for s in selected]

        print(f"\n[{i+1}/{len(listings)}] {pid} ({listing['condition']}) — tags: {image_tags}")

        entry = {
            "property_id": pid,
            "listing_url": listing["listing_url"],
            "condition": listing["condition"],
            "selected_tags": image_tags,
            "selected_urls": image_urls,
            "models": {},
        }

        for model_name, model_id in MODELS:
            t0 = time.time()
            resp = call_vision(model_id, image_urls)
            elapsed = time.time() - t0

            if resp["success"]:
                r = resp["result"]
                # Cost estimate
                cost = (resp["input_tokens"] * 0.80 / 1e6 + resp["output_tokens"] * 4.0 / 1e6) if model_name == "haiku" else \
                       (resp["input_tokens"] * 3.0 / 1e6 + resp["output_tokens"] * 15.0 / 1e6)
                total_cost[model_name] += cost

                entry["models"][model_name] = {
                    "is_render": r.get("is_render"),
                    "render_confidence": r.get("render_confidence"),
                    "condition_label": r.get("condition_label"),
                    "condition_confidence": r.get("condition_confidence"),
                    "finish_quality": r.get("finish_quality"),
                    "finish_quality_confidence": r.get("finish_quality_confidence"),
                    "input_tokens": resp["input_tokens"],
                    "output_tokens": resp["output_tokens"],
                    "cost_usd": round(cost, 5),
                    "latency_s": round(elapsed, 1),
                }
                print(f"  {model_name}: render={r.get('is_render')} cond={r.get('condition_label')} finish={r.get('finish_quality')} ({elapsed:.1f}s ${cost:.4f})")
            else:
                entry["models"][model_name] = {"error": resp["error"]}
                print(f"  {model_name}: FAILED — {resp['error']}")

            time.sleep(0.3)

        results.append(entry)

    # Save full results
    out_path = Path(__file__).parent / "phase0_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nFull results saved to {out_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print("SUMMARY — 30-Image Model Comparison")
    print("=" * 120)

    # Agreement stats
    agree_render = agree_condition = agree_finish = 0
    total_valid = 0
    for entry in results:
        h = entry["models"].get("haiku", {})
        s = entry["models"].get("sonnet", {})
        if "error" in h or "error" in s:
            continue
        total_valid += 1
        if h.get("is_render") == s.get("is_render"):
            agree_render += 1
        if h.get("condition_label") == s.get("condition_label"):
            agree_condition += 1
        if h.get("finish_quality") == s.get("finish_quality"):
            agree_finish += 1

    print(f"\nAgreement (Haiku vs Sonnet) on {total_valid} valid listings:")
    print(f"  Render:    {agree_render}/{total_valid} ({100*agree_render/total_valid:.0f}%)")
    print(f"  Condition: {agree_condition}/{total_valid} ({100*agree_condition/total_valid:.0f}%)")
    print(f"  Finish:    {agree_finish}/{total_valid} ({100*agree_finish/total_valid:.0f}%)")

    print(f"\nTotal cost:  Haiku ${total_cost['haiku']:.4f}  |  Sonnet ${total_cost['sonnet']:.4f}")
    print(f"Ratio: Sonnet is {total_cost['sonnet']/total_cost['haiku']:.1f}x more expensive")

    # Per-condition breakdown
    for cond in ["good", "newdevelopment", "renew"]:
        subset = [e for e in results if e["condition"] == cond and "error" not in e["models"].get("haiku", {}) and "error" not in e["models"].get("sonnet", {})]
        if not subset:
            continue
        print(f"\n--- {cond} ({len(subset)} listings) ---")
        print(f"{'PID':<12} {'Listing':<46} {'Tags':<30} {'H:render':>10} {'S:render':>10} {'H:cond':<25} {'S:cond':<25} {'H:finish':<12} {'S:finish':<12}")
        for e in subset:
            h, s = e["models"]["haiku"], e["models"]["sonnet"]
            tags_str = ",".join(e["selected_tags"])[:28]
            print(f"{e['property_id']:<12} {e['listing_url']:<46} {tags_str:<30} {str(h['is_render']):>10} {str(s['is_render']):>10} {h['condition_label']:<25} {s['condition_label']:<25} {h['finish_quality']:<12} {s['finish_quality']:<12}")

    print("\n" + "=" * 120)


if __name__ == "__main__":
    main()
