"""
Prompt Engineer Agent — Analyzes classification results and proposes prompt improvements.

Sends Claude a batch of edge-case listings (low confidence, cross-label mismatches)
along with the current prompt and distribution stats. Claude reviews the actual images,
identifies systematic weaknesses, and returns a refined prompt.

Usage:
  python prompt_engineer.py                           # auto-analyze edge cases
  python prompt_engineer.py survey_responses.json     # analyze with human feedback
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Current prompt (from the DAG) ────────────────────────────────────────────
CURRENT_PROMPT = """\
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


def load_edge_cases() -> list[dict]:
    """Load edge cases from pre-exported CSV."""
    cases = []
    csv_path = Path("/tmp/edge_cases.csv")
    for line in csv_path.read_text().strip().split("\n"):
        parts = line.split("|||")
        if len(parts) < 12:
            continue
        # Parse postgres array format {url1,url2,url3}
        urls_raw = parts[8].strip("{}")
        tags_raw = parts[9].strip("{}")
        urls = [u for u in urls_raw.split(",") if u]
        tags = [t for t in tags_raw.split(",") if t]
        cases.append({
            "property_id": parts[0],
            "case_type": parts[1],
            "condition_label": parts[2],
            "condition_confidence": float(parts[3]),
            "finish_quality": parts[4],
            "finish_quality_confidence": float(parts[5]),
            "is_render": parts[6] == "t",
            "render_confidence": float(parts[7]),
            "image_urls": urls,
            "image_tags": tags,
            "idealista_condition": parts[10],
            "listing_url": parts[11],
        })
    return cases


def load_distribution() -> str:
    """Load distribution stats."""
    csv_path = Path("/tmp/distribution.csv")
    lines = csv_path.read_text().strip().split("\n")
    table = "Feature | Label | Count | Avg Conf | Min Conf\n"
    table += "---|---|---|---|---\n"
    for line in lines:
        parts = line.split("|||")
        if len(parts) >= 5:
            table += " | ".join(parts) + "\n"
    return table


def load_survey_feedback(path: str) -> dict | None:
    """Load human evaluator feedback if provided."""
    try:
        with open(path) as f:
            data = json.load(f)
        # Also load ground truth from survey HTML
        html_path = Path(__file__).parent / "validation_survey.html"
        html = html_path.read_text()
        start = html.index('type="application/json">') + len('type="application/json">')
        end = html.index("</script>", start)
        ground_truth = json.loads(html[start:end])

        disagreements = []
        for pid, resp in data["responses"].items():
            gt = ground_truth.get(pid, {})
            if not gt:
                continue
            if resp.get("condition") and resp["condition"] != "uncertain" and resp["condition"] != gt["cv_condition"]:
                disagreements.append(f"  PID {pid}: Claude={gt['cv_condition']} (conf={gt['cv_condition_conf']}), Human={resp['condition']}. Notes: {resp.get('notes', '')}")
            if resp.get("finish_quality") and resp["finish_quality"] != "uncertain" and resp["finish_quality"] != gt["cv_finish"]:
                disagreements.append(f"  PID {pid}: Claude={gt['cv_finish']} (conf={gt['cv_finish_conf']}), Human={resp['finish_quality']}. Notes: {resp.get('notes', '')}")
            if resp.get("is_render") and resp["is_render"] != "uncertain":
                cv_render = "render" if gt["cv_is_render"] else "real"
                if resp["is_render"] != cv_render:
                    disagreements.append(f"  PID {pid}: Claude={cv_render} (conf={gt['cv_render_conf']}), Human={resp['is_render']}. Notes: {resp.get('notes', '')}")
        return {
            "evaluator": data.get("evaluator", "unknown"),
            "total_responses": len(data["responses"]),
            "disagreements": disagreements,
        }
    except Exception as e:
        print(f"Warning: could not load survey feedback: {e}")
        return None


def run_prompt_engineer(edge_cases: list[dict], distribution: str, survey: dict | None):
    """Send edge cases with images to Claude for prompt analysis."""

    # Build the analysis request with actual images
    content = []

    # System context
    analysis_intro = f"""# Prompt Engineering Task

You are a prompt engineer specializing in computer vision classification prompts.

## Your task
Analyze the current classification prompt, review the edge cases below (with actual images),
identify systematic weaknesses, and propose an improved prompt.

## Current prompt being used
```
{CURRENT_PROMPT}
```

## Distribution of 1,330 classified listings (Aveiro municipality, Portugal)
{distribution}

## Key observations from distribution
- "habitable" has the lowest avg confidence (0.776) — it's the hardest category
- 75% classified as "renovated" — possible over-classification bias
- 38% flagged as renders — these are mostly new development listings
- "standard" finish has low confidence (0.796) — blurry boundary with premium

"""

    if survey:
        analysis_intro += f"""## Human evaluator feedback ({survey['evaluator']})
{survey['total_responses']} listings reviewed. Disagreements:
""" + "\n".join(survey["disagreements"][:30]) + "\n\n"

    analysis_intro += """## Edge cases to review
Below are listings where the model had low confidence or produced unexpected results.
For each one I'm showing you the same images that were sent to the model.
Analyze what makes these cases difficult and how the prompt could handle them better.

"""
    content.append({"type": "text", "text": analysis_intro})

    # Add edge cases with images (limit to 15 to stay within token budget)
    for case in edge_cases[:15]:
        case_text = (
            f"\n### Case: {case['property_id']} — {case['case_type']}\n"
            f"Idealista condition: {case['idealista_condition']} | "
            f"CV condition: {case['condition_label']} (conf={case['condition_confidence']}) | "
            f"CV finish: {case['finish_quality']} (conf={case['finish_quality_confidence']}) | "
            f"CV render: {case['is_render']} (conf={case['render_confidence']})\n"
            f"Tags: {', '.join(case['image_tags'])}\n"
            f"Listing: {case['listing_url']}\n"
        )
        content.append({"type": "text", "text": case_text})

        # Add actual images
        for url in case["image_urls"][:3]:
            if url:
                content.append({"type": "image", "source": {"type": "url", "url": url}})

    # Final instruction
    content.append({"type": "text", "text": """
## Instructions

After reviewing all the edge cases above, provide:

1. **Diagnosis** — What systematic weaknesses do you see in the current prompt? Which label boundaries are most problematic? What visual cues is the model missing or misinterpreting?

2. **Specific improvements** — For each weakness, describe the exact change needed. Be concrete: "add X to the definition of Y" not "improve definitions".

3. **Revised prompt** — Write the complete improved prompt (same JSON schema, same 3 features). Keep it concise but more precise. The prompt must still say "Return ONLY a single JSON object" and "Do NOT return an array".

4. **Expected impact** — Which edge case types should improve, and by how much (rough estimate).

Format the revised prompt in a ```markdown code block so it can be copy-pasted directly.
"""})

    print("Sending 15 edge cases with images to Claude for analysis...")
    print("(This may take 30-60 seconds due to image processing)\n")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    return response.content[0].text


def main():
    edge_cases = load_edge_cases()
    distribution = load_distribution()
    print(f"Loaded {len(edge_cases)} edge cases")

    survey = None
    if len(sys.argv) > 1:
        survey = load_survey_feedback(sys.argv[1])
        if survey:
            print(f"Loaded survey feedback: {survey['total_responses']} responses, {len(survey['disagreements'])} disagreements")

    result = run_prompt_engineer(edge_cases, distribution, survey)

    # Save result
    out_path = Path(__file__).parent / "prompt_engineer_analysis.md"
    out_path.write_text(result)
    print(f"\n{'=' * 80}")
    print(result)
    print(f"\n{'=' * 80}")
    print(f"\nFull analysis saved to {out_path}")

    # Extract the revised prompt if present
    if "```" in result:
        blocks = result.split("```")
        for i, block in enumerate(blocks):
            if i % 2 == 1 and "is_render" in block:
                # Remove language tag if present
                prompt_text = block.strip()
                if prompt_text.startswith(("markdown", "text", "json")):
                    prompt_text = prompt_text.split("\n", 1)[1] if "\n" in prompt_text else prompt_text
                revised_path = Path(__file__).parent / "revised_prompt.txt"
                revised_path.write_text(prompt_text.strip())
                print(f"Revised prompt extracted to {revised_path}")
                break


if __name__ == "__main__":
    main()
