#!/usr/bin/env python3
"""Offline consistency check for the four camera-ready headline values."""

import json
import math
from pathlib import Path

try:
    from _bootstrap import REPO_ROOT
except ModuleNotFoundError:  # imported as scripts.verify_reported_numbers
    from scripts._bootstrap import REPO_ROOT
from src.evaluation.summary import aggregate_correctness, load_compact_rows, matching_rows

EXPECTED = (
    ("full_abnormal_gpt51_joint_false_text", "gemini_generated.jsonl", "gemini_generated", "baseline_rag", 499, 0.07915831663326653, "7.9%"),
    ("full_abnormal_gpt51_witness_only_false_text", "gemini_generated.jsonl", "gemini_generated", "witness_only", 499, 0.8416833667334669, "84.2%"),
    ("gpt4o_abnormal_gpt51_joint_false_text", "gpt4o_regenerated.jsonl", "gpt4o_regenerated", "baseline_rag", 100, 0.68, "68.0%"),
    ("gpt4o_abnormal_gpt51_full_witness_arbiter_false_text", "gpt4o_regenerated.jsonl", "gpt4o_regenerated", "s2va", 100, 0.85, "85.0%"),
)


def verify(root: Path | str = REPO_ROOT) -> dict[str, object]:
    root = Path(root)
    cache = {}
    results = []
    failures = []
    for name, filename, split, phase, expected_n, expected_mean, displayed in EXPECTED:
        if filename not in cache:
            cache[filename] = load_compact_rows([root / "results" / "compact" / filename])
        filters = {
            "generator_source_split": split,
            "image_type": "abnormal",
            "model_id": "openai/gpt-5.1",
            "experimental_phase": phase,
            "text_condition": "false_text",
            "attack_condition": "none",
        }
        aggregate = aggregate_correctness(matching_rows(cache[filename], **filters))
        passed = aggregate["n"] == expected_n and math.isclose(aggregate["mean"], expected_mean, rel_tol=0.0, abs_tol=1e-12)
        result = {"name": name, "filters": filters, "expected_n": expected_n, "observed_n": aggregate["n"], "expected_mean": expected_mean, "observed_mean": aggregate["mean"], "displayed": displayed, "passed": passed}
        results.append(result)
        if not passed:
            failures.append(name)
    payload = {"schema_version": 1, "all_passed": not failures, "results": results}
    output = root / "results" / "summaries" / "headline_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("Headline verification failed: " + ", ".join(failures))
    return payload


if __name__ == "__main__":
    for result in verify()["results"]:
        print(f"PASS {result['name']}: n={result['observed_n']}, mean={result['observed_mean']:.15g} ({result['displayed']})")
