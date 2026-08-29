#!/usr/bin/env python3
"""Offline consistency checks for released camera-ready aggregates."""

import json
import math
from pathlib import Path

try:
    from _bootstrap import REPO_ROOT
except ModuleNotFoundError:  # imported as scripts.verify_reported_numbers
    from scripts._bootstrap import REPO_ROOT


HEADLINE_EXPECTED = {
    "full_abnormal_gemini_false_text": {
        "n": 499,
        "joint": 0.07915831663326653,
        "witness_only": 0.4969939879759519,
        "leaky_witness": 0.6372745490981964,
        "s2va": 0.8416833667334669,
    },
    "gpt4o_regenerated_abnormal_false_text": {
        "n": 100,
        "joint": 0.68,
        "witness_only": 0.61,
        "s2va": 0.85,
    },
}

SUMMARY_EXPECTED = {
    "main": {
        "openai_gpt-5.1": (499, 0.4969939879759519, 0.8416833667334669),
        "google_gemini-2.5-pro": (499, 0.5490981963927856, 0.8637274549098196),
        "qwen_qwen3-vl-235b-a22b-thinking": (499, 0.3587174348697395, 0.7995991983967936),
        "anthropic_claude-sonnet-4.5": (499, 0.3967935871743487, 0.7985971943887775),
        "moonshotai_kimi-k2.5": (499, 0.3246492985971944, 0.5881763527054108),
        "qwen_qwen3-vl-235b-a22b-instruct": (499, 0.48296593186372744, 0.6803607214428857),
    },
    "cross_generator": {
        "openai_gpt-5.1": (100, 0.61, 0.85),
        "google_gemini-2.5-pro": (100, 0.60, 0.85),
        "qwen_qwen3-vl-235b-a22b-instruct": (100, 0.54, 0.68),
        "moonshotai_kimi-k2.5": (100, 0.59, 0.72),
    },
}


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)


def verify(root: Path | str = REPO_ROOT) -> dict[str, object]:
    root = Path(root)
    failures = []

    headline = json.loads((root / "results" / "summaries" / "headline_results.json").read_text(encoding="utf-8"))
    if headline.get("camera_ready") != HEADLINE_EXPECTED:
        failures.append("headline_results")

    summary = json.loads((root / "results" / "summaries" / "witness_only_corrected_results.json").read_text(encoding="utf-8"))
    summary_results = []
    for split, models in SUMMARY_EXPECTED.items():
        observed_models = summary.get(split, {})
        if set(observed_models) != set(models):
            failures.append(f"{split}_model_set")
        for model, (expected_n, expected_witness, expected_s2va) in models.items():
            row = observed_models.get(model, {})
            n = row.get("n")
            witness = row.get("corrected_witness_accuracy")
            s2va = row.get("s2va_accuracy")
            improve = row.get("s2va_improved_count")
            degrade = row.get("s2va_degraded_count")
            same = row.get("unchanged_count")
            changed = row.get("score_change_count")
            gain = row.get("s2va_minus_witness_pp")
            passed = (
                n == expected_n
                and isinstance(witness, (int, float))
                and isinstance(s2va, (int, float))
                and close(witness, expected_witness)
                and close(s2va, expected_s2va)
                and improve + degrade + same == n
                and improve + degrade == changed
                and close(gain, 100.0 * (s2va - witness))
            )
            name = f"{split}:{model}"
            summary_results.append({"name": name, "n": n, "witness": witness, "s2va": s2va, "passed": passed})
            if not passed:
                failures.append(name)

    if summary.get("completed_labels") != 3394 or summary.get("failed_labels") != 0:
        failures.append("corrected_label_totals")

    main_gpt = summary["main"]["openai_gpt-5.1"]
    cross_gpt = summary["cross_generator"]["openai_gpt-5.1"]
    main_headline = headline["camera_ready"]["full_abnormal_gemini_false_text"]
    cross_headline = headline["camera_ready"]["gpt4o_regenerated_abnormal_false_text"]
    if not close(main_headline["witness_only"], main_gpt["corrected_witness_accuracy"]):
        failures.append("main_headline_witness_link")
    if not close(main_headline["s2va"], main_gpt["s2va_accuracy"]):
        failures.append("main_headline_s2va_link")
    if not close(cross_headline["witness_only"], cross_gpt["corrected_witness_accuracy"]):
        failures.append("cross_headline_witness_link")
    if not close(cross_headline["s2va"], cross_gpt["s2va_accuracy"]):
        failures.append("cross_headline_s2va_link")

    payload = {"all_passed": not failures, "corrected_witness": summary_results, "failures": failures}
    if failures:
        raise SystemExit("Camera-ready verification failed: " + ", ".join(failures))
    return payload


if __name__ == "__main__":
    payload = verify()
    print("PASS camera-ready headline table")
    for result in payload["corrected_witness"]:
        print(f"PASS {result['name']}: n={result['n']}, witness={result['witness']:.6f}, s2va={result['s2va']:.6f}")

