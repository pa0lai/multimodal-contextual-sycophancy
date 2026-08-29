"""
W5: Bootstrap 95% confidence intervals for correctness scores.

Reads all evaluated JSONL files in results/ and computes bootstrap CIs
for each (model, phase, condition) cell.

Usage:
    python scripts/compute_bootstrap_ci.py \
        --results_dir results \
        --n_bootstrap 10000 \
        --output results/bootstrap_ci.json \
        --phases baseline_rag s2va witness_only cot_rag two_call_rag param_only \
        --conditions false_text true_text irrelevant_text none
"""

import argparse
import json
import os
import random
from collections import defaultdict
from typing import Dict, List, Tuple

from _bootstrap import REPO_ROOT  # noqa: F401


def bootstrap_ci(
    scores: List[float], n: int = 10000, alpha: float = 0.05, seed: int = 42
) -> Tuple[float, float, float]:
    """Return (mean, lower, upper) bootstrap CI."""
    rng = random.Random(seed)
    k = len(scores)
    if k == 0:
        return (float("nan"), float("nan"), float("nan"))
    means = []
    for _ in range(n):
        resample = [scores[rng.randint(0, k - 1)] for _ in range(k)]
        means.append(sum(resample) / k)
    means.sort()
    lo = means[int(alpha / 2 * n)]
    hi = means[int((1 - alpha / 2) * n)]
    return (sum(scores) / k, lo, hi)


def collect_scores(
    results_dir: str,
    target_phases: List[str],
    target_conditions: List[str],
) -> Dict[Tuple[str, str, str], List[float]]:
    """Return dict keyed by (model_slug, phase, condition) → list of correctness scores."""
    data: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)

    for root, _dirs, files in os.walk(results_dir):
        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(root, fname)

            # Determine phase from path
            matched_phase = None
            for ph in target_phases:
                if f"/{ph}/" in fpath or fpath.endswith(f"/{ph}.jsonl"):
                    matched_phase = ph
                    break
            if matched_phase is None:
                continue

            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    score = d.get("correctness_score")
                    if score is None:
                        continue
                    condition = d.get("condition", "none")
                    if target_conditions and condition not in target_conditions:
                        continue
                    model = d.get("model_name") or d.get("metadata", {}).get("model", "unknown")
                    # Normalise model slug (some entries store full "openai/gpt-5.1", others slug)
                    model_slug = model.replace("/", "_")
                    data[(model_slug, matched_phase, condition)].append(float(score))

    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results_dir", default="results")
    parser.add_argument("--n_bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/bootstrap_ci.json")
    parser.add_argument(
        "--phases",
        nargs="+",
        default=[
            "param_only", "baseline_rag", "s2va", "cot_rag",
            "witness_only", "visual_supremacy_only", "dose_response",
            "two_call_rag",
        ],
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["false_text", "true_text", "irrelevant_text", "none",
                 "weak_text", "medium_text", "strong_text",
                 "no_context", "correct_context", "shuffled_context"],
    )
    args = parser.parse_args()

    print("Collecting scores ...")
    data = collect_scores(args.results_dir, args.phases, args.conditions)
    print(f"Found {len(data)} (model, phase, condition) cells.")

    results = {}
    for (model, phase, condition), scores in sorted(data.items()):
        mean, lo, hi = bootstrap_ci(scores, n=args.n_bootstrap, seed=args.seed)
        key = f"{model}__{phase}__{condition}"
        results[key] = {
            "model": model,
            "phase": phase,
            "condition": condition,
            "n": len(scores),
            "mean": round(mean, 4),
            "ci_lower": round(lo, 4),
            "ci_upper": round(hi, 4),
            "ci_width": round(hi - lo, 4),
        }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    # Print compact table
    print(f"\n{'Model':<40} {'Phase':<22} {'Cond':<20} {'N':>5} {'Mean':>6}  {'95% CI'}")
    print("-" * 115)
    for key, r in sorted(results.items()):
        print(
            f"{r['model']:<40} {r['phase']:<22} {r['condition']:<20} "
            f"{r['n']:>5} {r['mean']:>6.3f}  [{r['ci_lower']:.3f}, {r['ci_upper']:.3f}]"
        )

    print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    main()
