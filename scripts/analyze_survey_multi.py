"""
Multi-evaluator survey analysis with inter-rater reliability.

Usage: python analyze_survey_multi.py survey_responses_*.json

Computes:
  - Cohen's kappa between each pair of evaluators (per feature)
  - Per-evaluator agreement rates vs Claude ground truth
  - Consensus labels (both agree = ground truth, disagree = disputed)

Outputs:
  - scripts/survey_consensus.json
  - scripts/survey_inter_rater.json
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


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Compute Cohen's kappa for two lists of categorical labels."""
    assert len(labels_a) == len(labels_b)
    n = len(labels_a)
    if n == 0:
        return float("nan")

    categories = sorted(set(labels_a) | set(labels_b))
    confusion = Counter(zip(labels_a, labels_b))

    # Observed agreement
    po = sum(confusion[(c, c)] for c in categories) / n

    # Expected agreement (by chance)
    pe = 0.0
    for c in categories:
        row_marginal = sum(1 for a in labels_a if a == c) / n
        col_marginal = sum(1 for b in labels_b if b == c) / n
        pe += row_marginal * col_marginal

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def kappa_interpretation(k: float) -> str:
    if k < 0.0:
        return "poor"
    if k < 0.20:
        return "slight"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial"
    return "almost perfect"


# ── Render mapping ───────────────────────────────────────────────────────────
# Paula uses "mixed" and "uncertain"; DCL is binary (real/render).
# For kappa: exclude "uncertain" and "mixed" (abstentions).
# For consensus: "mixed" treated as abstention.

ABSTAIN = {"uncertain", "mixed"}


def normalize_render(val: str) -> str | None:
    """Map render responses to binary (real/render) or None for abstentions."""
    if val in ABSTAIN:
        return None
    return val  # "real" or "render"


def analyze_multi(response_files: list[str]):
    ground_truth = extract_ground_truth(SURVEY_HTML)

    evaluators = []
    for path in response_files:
        with open(path) as f:
            data = json.load(f)
        evaluators.append(data)

    names = [e.get("evaluator", f"eval_{i}") for i, e in enumerate(evaluators)]
    all_pids = sorted(set().union(*(e["responses"].keys() for e in evaluators)))

    print(f"Evaluators: {', '.join(names)}")
    print(f"Properties: {len(all_pids)}")
    print()

    # ── Inter-rater reliability (pairwise) ───────────────────────────────────
    inter_rater = {"evaluators": names, "features": {}}

    for feature, get_label in [
        ("condition", lambda r: r.get("condition")),
        ("finish_quality", lambda r: r.get("finish_quality")),
        ("render", lambda r: normalize_render(r.get("is_render", ""))),
    ]:
        # Collect paired labels where both evaluators gave a non-abstain answer
        pairs = []
        for pid in all_pids:
            labels = []
            for ev in evaluators:
                resp = ev["responses"].get(pid, {})
                label = get_label(resp)
                if label and label not in ABSTAIN:
                    labels.append(label)
                else:
                    labels.append(None)
            if all(l is not None for l in labels):
                pairs.append(tuple(labels))

        if not pairs:
            inter_rater["features"][feature] = {
                "n": 0, "kappa": None, "interpretation": "N/A",
                "agreement_rate": "N/A",
            }
            continue

        labels_a = [p[0] for p in pairs]
        labels_b = [p[1] for p in pairs]

        agree = sum(1 for a, b in pairs if a == b)
        n = len(pairs)
        k = cohens_kappa(labels_a, labels_b)

        # Confusion matrix between evaluators
        categories = sorted(set(labels_a) | set(labels_b))
        confusion = {}
        for ca in categories:
            for cb in categories:
                count = sum(1 for a, b in pairs if a == ca and b == cb)
                if count > 0:
                    confusion[f"{ca} vs {cb}"] = count

        inter_rater["features"][feature] = {
            "n": n,
            "agreement_rate": f"{agree}/{n} ({100*agree/n:.0f}%)",
            "kappa": round(k, 3),
            "interpretation": kappa_interpretation(k),
            "confusion": confusion,
        }

        print(f"--- {feature.upper()} (inter-rater) ---")
        print(f"  Paired observations: {n}")
        print(f"  Agreement: {agree}/{n} ({100*agree/n:.0f}%)")
        print(f"  Cohen's kappa: {k:.3f} ({kappa_interpretation(k)})")

        # Print confusion matrix
        header = f"  {names[0]:<20}" + "".join(f"{c:>18}" for c in categories)
        print(header)
        for ca in categories:
            row = f"  {ca:<20}"
            for cb in categories:
                count = sum(1 for a, b in pairs if a == ca and b == cb)
                row += f"{count:>18}"
            print(row)
        print()

    # ── Per-evaluator agreement vs Claude ────────────────────────────────────
    print("=" * 60)
    print("EVALUATOR vs CLAUDE AGREEMENT")
    print("=" * 60)

    evaluator_vs_claude = {}
    for i, ev in enumerate(evaluators):
        name = names[i]
        stats = {}
        for feature, cv_key, get_label in [
            ("condition", "cv_condition", lambda r: r.get("condition")),
            ("finish_quality", "cv_finish", lambda r: r.get("finish_quality")),
            ("render", "cv_is_render", lambda r: normalize_render(r.get("is_render", ""))),
        ]:
            agree = total = 0
            for pid, resp in ev["responses"].items():
                gt = ground_truth.get(pid, {})
                if not gt:
                    continue
                label = get_label(resp)
                if label is None or label in ABSTAIN:
                    continue
                total += 1
                cv_val = gt[cv_key]
                # Render is boolean in ground truth
                if feature == "render":
                    cv_val = "render" if cv_val else "real"
                if cv_val == label:
                    agree += 1
            pct = f"{agree}/{total} ({100*agree/total:.0f}%)" if total > 0 else "N/A"
            stats[feature] = {"agree": agree, "total": total, "rate": pct}

        evaluator_vs_claude[name] = stats
        print(f"\n  {name}:")
        for feat, s in stats.items():
            print(f"    {feat:<18} {s['rate']}")

    inter_rater["evaluator_vs_claude"] = evaluator_vs_claude

    # ── Consensus labels ─────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("CONSENSUS GROUND TRUTH")
    print("=" * 60)

    consensus = {}
    stats = {"agreed": 0, "one_abstained": 0, "disputed": 0, "both_abstained": 0}

    for pid in all_pids:
        gt = ground_truth.get(pid, {})
        entry = {"property_id": pid, "claude": {}, "consensus": {}, "evaluator_labels": {}}

        if gt:
            entry["claude"] = {
                "condition": gt.get("cv_condition"),
                "finish_quality": gt.get("cv_finish"),
                "is_render": gt.get("cv_is_render"),
                "condition_conf": gt.get("cv_condition_conf"),
                "finish_conf": gt.get("cv_finish_conf"),
                "render_conf": gt.get("cv_render_conf"),
            }

        for feature, get_label in [
            ("condition", lambda r: r.get("condition")),
            ("finish_quality", lambda r: r.get("finish_quality")),
            ("render", lambda r: normalize_render(r.get("is_render", ""))),
        ]:
            labels = []
            for j, ev in enumerate(evaluators):
                resp = ev["responses"].get(pid, {})
                label = get_label(resp)
                if label and label not in ABSTAIN:
                    labels.append((names[j], label))
                else:
                    labels.append((names[j], None))

            entry["evaluator_labels"][feature] = {
                name: label for name, label in labels
            }

            non_null = [(name, label) for name, label in labels if label is not None]

            if len(non_null) == 0:
                entry["consensus"][feature] = {"label": None, "status": "both_abstained"}
                stats["both_abstained"] += 1
            elif len(non_null) == 1:
                entry["consensus"][feature] = {
                    "label": non_null[0][1],
                    "status": "one_abstained",
                    "source": non_null[0][0],
                }
                stats["one_abstained"] += 1
            elif non_null[0][1] == non_null[1][1]:
                entry["consensus"][feature] = {
                    "label": non_null[0][1],
                    "status": "agreed",
                }
                stats["agreed"] += 1
            else:
                entry["consensus"][feature] = {
                    "label": None,
                    "status": "disputed",
                    "labels": {name: label for name, label in non_null},
                }
                stats["disputed"] += 1

        consensus[pid] = entry

    total_decisions = stats["agreed"] + stats["one_abstained"] + stats["disputed"] + stats["both_abstained"]
    print(f"  Agreed:         {stats['agreed']}/{total_decisions} ({100*stats['agreed']/total_decisions:.0f}%)")
    print(f"  One abstained:  {stats['one_abstained']}/{total_decisions} ({100*stats['one_abstained']/total_decisions:.0f}%)")
    print(f"  Disputed:       {stats['disputed']}/{total_decisions} ({100*stats['disputed']/total_decisions:.0f}%)")
    print(f"  Both abstained: {stats['both_abstained']}/{total_decisions} ({100*stats['both_abstained']/total_decisions:.0f}%)")

    # ── Disputed details ─────────────────────────────────────────────────────
    disputed = []
    for pid, entry in consensus.items():
        for feature, cons in entry["consensus"].items():
            if cons["status"] == "disputed":
                cv_label = entry["claude"].get(feature if feature != "render" else "is_render")
                if feature == "render" and isinstance(cv_label, bool):
                    cv_label = "render" if cv_label else "real"
                disputed.append({
                    "pid": pid,
                    "feature": feature,
                    "evaluator_labels": cons["labels"],
                    "claude": cv_label,
                })

    if disputed:
        print(f"\n  DISPUTED LABELS ({len(disputed)}):")
        for d in sorted(disputed, key=lambda x: (x["feature"], x["pid"])):
            labels_str = " vs ".join(f"{k}={v}" for k, v in d["evaluator_labels"].items())
            print(f"    [{d['feature']}] {d['pid']}: {labels_str} (Claude={d['claude']})")

    # ── Claude vs consensus agreement ────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("CLAUDE vs CONSENSUS (where evaluators agreed)")
    print("=" * 60)

    for feature in ["condition", "finish_quality", "render"]:
        agree = total = 0
        for pid, entry in consensus.items():
            cons = entry["consensus"][feature]
            if cons["status"] != "agreed":
                continue
            total += 1
            cv_key = feature if feature != "render" else "is_render"
            cv_label = entry["claude"].get(cv_key)
            if feature == "render" and isinstance(cv_label, bool):
                cv_label = "render" if cv_label else "real"
            if cv_label == cons["label"]:
                agree += 1
        pct = f"{agree}/{total} ({100*agree/total:.0f}%)" if total > 0 else "N/A"
        print(f"  {feature:<18} {pct}")

    # ── Save outputs ─────────────────────────────────────────────────────────
    out_dir = Path(__file__).parent

    consensus_path = out_dir / "survey_consensus.json"
    consensus_path.write_text(json.dumps(consensus, indent=2, ensure_ascii=False))
    print(f"\nConsensus saved to {consensus_path}")

    inter_rater_path = out_dir / "survey_inter_rater.json"
    inter_rater_path.write_text(json.dumps(inter_rater, indent=2, ensure_ascii=False))
    print(f"Inter-rater saved to {inter_rater_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyze_survey_multi.py <response1.json> <response2.json> [...]")
        sys.exit(1)
    analyze_multi(sys.argv[1:])
