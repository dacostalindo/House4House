"""
Phase 0 — Pre-flight URL Accessibility Test + Model Comparison

Tests 5 sample image URLs from raw_idealista against Claude Vision API.
Confirms that Idealista CDN images are accessible server-side (no 403/placeholder).
Compares Haiku vs Sonnet responses on the same images.
"""

import json
import os
import time

import anthropic

# Load API key from .env
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# 5 sample image URLs from the warehouse query
SAMPLE_IMAGES = [
    {
        "property_id": "34620432",
        "url": "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/85/ef/13/301153221.webp",
        "tag": "facade",
    },
    {
        "property_id": "34577730",
        "url": "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/27/1a/1a/299309273.webp",
        "tag": "bedroom",
    },
    {
        "property_id": "34890849",
        "url": "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/4e/29/07/311541418.webp",
        "tag": "swimmingPool",
    },
    {
        "property_id": "34733103",
        "url": "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/ac/45/57/305401159.webp",
        "tag": "corridor",
    },
    {
        "property_id": "31429870",
        "url": "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/17/06/6d/154465253.webp",
        "tag": "facade",
    },
]

PROMPT = """\
You are a real estate image analyst. Analyze this property listing image and return a single JSON object with exactly these fields:

{
  "is_render": true/false,
  "render_confidence": 0.0-1.0,
  "condition_label": "needs_renovation" | "habitable" | "renovated",
  "condition_confidence": 0.0-1.0,
  "finish_quality": "basic" | "standard" | "premium",
  "finish_quality_confidence": 0.0-1.0
}

Definitions:
- is_render: TRUE if the image is a 3D render/CGI (not a real photograph).
- condition_label:
  - needs_renovation: any level of renovation needed — from cosmetic updates to full structural work
  - habitable: functional and livable as-is — clean, maintained, no visible damage, but not recently updated
  - renovated: clearly new or recently updated materials — fresh paint, modern fixtures, new appliances
- finish_quality:
  - basic: laminate/vinyl floors, basic white tiles, no-name appliances, cheap materials
  - standard: ceramic tile/laminate, standard kitchen, functional bathroom, decent but unremarkable
  - premium: hardwood/marble floors, quality kitchen (stone counters, branded appliances), modern bathroom, designer fixtures

Return ONLY a single JSON object, no other text. Do NOT return an array."""

MODELS = [
    ("haiku", "claude-haiku-4-5-20251001"),
    ("sonnet", "claude-sonnet-4-20250514"),
]


def call_vision(model_id: str, image_url: str) -> dict:
    """Call Claude Vision with a single image URL. Returns parsed JSON or error dict."""
    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "url", "url": image_url}},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        parsed = json.loads(raw)
        return {
            "success": True,
            "result": parsed,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def main():
    print("=" * 80)
    print("PHASE 0 — Pre-flight URL Accessibility + Model Comparison")
    print("=" * 80)

    for img in SAMPLE_IMAGES:
        print(f"\n{'─' * 80}")
        print(f"Property: {img['property_id']}  |  Tag: {img['tag']}")
        print(f"URL: {img['url']}")
        print(f"{'─' * 80}")

        for model_name, model_id in MODELS:
            print(f"\n  [{model_name.upper()}] Calling {model_id}...")
            t0 = time.time()
            result = call_vision(model_id, img["url"])
            elapsed = time.time() - t0

            if result["success"]:
                r = result["result"]
                print(f"  ✓ Response in {elapsed:.1f}s  (in: {result['input_tokens']}, out: {result['output_tokens']})")
                print(f"    is_render:     {r.get('is_render')}  (conf: {r.get('render_confidence')})")
                print(f"    condition:     {r.get('condition_label')}  (conf: {r.get('condition_confidence')})")
                print(f"    finish:        {r.get('finish_quality')}  (conf: {r.get('finish_quality_confidence')})")
            else:
                print(f"  ✗ FAILED in {elapsed:.1f}s: {result['error']}")

            time.sleep(0.5)  # gentle rate limit

    print(f"\n{'=' * 80}")
    print("Pre-flight complete. Review results above.")
    print("=" * 80)


if __name__ == "__main__":
    main()
