"""
Analyze survey responses vs Claude Vision ground truth.

Usage: python analyze_survey.py survey_responses_2026-03-23.json

Computes per-feature agreement rates and confusion matrices.
Outputs prompt improvement suggestions based on disagreements.
"""

import json
import sys
from collections import Counter
from pathlib import Path

SURVEY_HTML = Path(__file__).parent / "validation_survey.html"


def extract_ground_truth(html_path: Path) -> dict:
    """Extract Claude's labels from the hidden <script> tag in the survey HTML."""
    html = html_path.read_text()
    start = html.index('type="application/json">') + len('type="application/json">')
    end = html.index("</script>", start)
    return json.loads(html[start:end])


def analyze(response_file: str):
    ground_truth = extract_ground_truth(SURVEY_HTML)
    with open(response_file) as f:
        data = json.load(f)

    evaluator = data.get("evaluator", "unknown")
    responses = data["responses"]

    print(f"Evaluator: {evaluator}")
    print(f"Timestamp: {data.get('timestamp', 'N/A')}")
    print(f"Responses: {len(responses)}")
    print()

    # ── Per-feature agreement ─────────────────────────────────────────────
    condition_agree = condition_total = 0
    finish_agree = finish_total = 0
    render_agree = render_total = 0

    condition_confusion = Counter()
    finish_confusion = Counter()
    render_confusion = Counter()
    disagreements = []

    for pid, resp in responses.items():
        gt = ground_truth.get(pid, {})
        if not gt:
            continue

        # Condition
        if resp.get("condition") and resp["condition"] != "uncertain":
            condition_total += 1
            cv = gt["cv_condition"]
            ev = resp["condition"]
            condition_confusion[(cv, ev)] += 1
            if cv == ev:
                condition_agree += 1
            else:
                disagreements.append({
                    "pid": pid, "feature": "condition",
                    "claude": cv, "evaluator": ev,
                    "confidence": gt["cv_condition_conf"],
                    "notes": resp.get("notes", ""),
                })

        # Finish quality
        if resp.get("finish_quality") and resp["finish_quality"] != "uncertain":
            finish_total += 1
            cv = gt["cv_finish"]
            ev = resp["finish_quality"]
            finish_confusion[(cv, ev)] += 1
            if cv == ev:
                finish_agree += 1
            else:
                disagreements.append({
                    "pid": pid, "feature": "finish",
                    "claude": cv, "evaluator": ev,
                    "confidence": gt["cv_finish_conf"],
                    "notes": resp.get("notes", ""),
                })

        # Render
        if resp.get("is_render") and resp["is_render"] != "uncertain":
            render_total += 1
            cv_render = gt["cv_is_render"]
            ev_render = resp["is_render"] == "render"
            render_confusion[(cv_render, ev_render)] += 1
            if cv_render == ev_render:
                render_agree += 1
            else:
                disagreements.append({
                    "pid": pid, "feature": "render",
                    "claude": "render" if cv_render else "real",
                    "evaluator": resp["is_render"],
                    "confidence": gt["cv_render_conf"],
                    "notes": resp.get("notes", ""),
                })

    # ── Results ───────────────────────────────────────────────────────────
    print("=" * 60)
    print("AGREEMENT RATES")
    print("=" * 60)

    def pct(n, d):
        return f"{n}/{d} ({100*n/d:.0f}%)" if d > 0 else "N/A"

    print(f"  Condition:     {pct(condition_agree, condition_total)}")
    print(f"  Finish:        {pct(finish_agree, finish_total)}")
    print(f"  Render:        {pct(render_agree, render_total)}")

    # ── Confusion matrices ────────────────────────────────────────────────
    for name, confusion, labels in [
        ("CONDITION", condition_confusion, ["needs_renovation", "habitable", "renovated"]),
        ("FINISH QUALITY", finish_confusion, ["basic", "standard", "premium"]),
    ]:
        print(f"\n--- {name} confusion (Claude rows, Evaluator cols) ---")
        header = f"{'Claude':<20}" + "".join(f"{l:>18}" for l in labels)
        print(header)
        for cl in labels:
            row = f"{cl:<20}"
            for el in labels:
                count = confusion.get((cl, el), 0)
                row += f"{count:>18}"
            print(row)

    # ── Disagreement details ──────────────────────────────────────────────
    if disagreements:
        print(f"\n{'=' * 60}")
        print(f"DISAGREEMENTS ({len(disagreements)} total)")
        print("=" * 60)
        for d in sorted(disagreements, key=lambda x: x["feature"]):
            notes = f" — {d['notes']}" if d["notes"] else ""
            print(f"  [{d['feature']}] {d['pid']}: Claude={d['claude']} vs Evaluator={d['evaluator']} (conf={d['confidence']}){notes}")

    # ── Save analysis ─────────────────────────────────────────────────────
    analysis = {
        "evaluator": evaluator,
        "agreement": {
            "condition": {"agree": condition_agree, "total": condition_total},
            "finish": {"agree": finish_agree, "total": finish_total},
            "render": {"agree": render_agree, "total": render_total},
        },
        "disagreements": disagreements,
    }
    out = Path(response_file).with_suffix(".analysis.json")
    out.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
    print(f"\nAnalysis saved to {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_survey.py <survey_responses.json>")
        sys.exit(1)
    analyze(sys.argv[1])
