"""
Derive a witness-only control file from existing S2VA outputs.

This does not rerun inference. It reuses the blind witness reports already
stored in s2va result files and converts them into standalone witness_only
results that can be evaluated with the standard judge pipeline.

Usage:
    python scripts/derive_witness_only.py --results_dir results
"""

import argparse
import glob
import json
import os
from typing import Dict, Any, List


def derive_file(input_file: str, output_file: str) -> int:
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    count = 0
    with open(input_file, "r") as fin, open(output_file, "w") as fout:
        for line in fin:
            if not line.strip():
                continue
            data: Dict[str, Any] = json.loads(line)
            derived = dict(data)
            derived["inference_type"] = "witness_only"
            derived["final_answer"] = data.get("visual_testimony") or data.get("final_answer", "")
            derived["metadata"] = dict(data.get("metadata", {}))
            derived["metadata"]["derived_from"] = input_file
            derived["metadata"]["control_type"] = "witness_only"
            # Witness-only is context-free by construction.
            derived["text_faithfulness_score"] = None
            fout.write(json.dumps(derived) + "\n")
            count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="Derive witness_only results from S2VA outputs")
    parser.add_argument("--results_dir", type=str, default="results", help="Root results directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing witness_only files")
    args = parser.parse_args()

    input_files = glob.glob(os.path.join(args.results_dir, "**", "s2va", "**", "*.jsonl"), recursive=True)
    if not input_files:
        print("No S2VA result files found.")
        return

    total = 0
    written = 0
    for input_file in input_files:
        if "/s2va/" not in input_file.replace("\\", "/"):
            continue
        if "/s2va_leaky/" in input_file.replace("\\", "/"):
            continue

        rel = os.path.relpath(input_file, args.results_dir)
        parts = rel.split(os.sep)
        if len(parts) < 4:
            continue

        model_slug = parts[0]
        # results/<model>/s2va/<attack>/<condition>.jsonl
        if parts[1] != "s2va":
            continue

        attack = parts[2]
        condition_file = parts[3]
        output_file = os.path.join(args.results_dir, model_slug, "witness_only", attack, condition_file)
        if os.path.exists(output_file) and not args.overwrite:
            continue

        count = derive_file(input_file, output_file)
        total += count
        written += 1
        print(f"Derived {count} rows -> {output_file}")

    print(f"Done. Wrote {written} files with {total} rows total.")


if __name__ == "__main__":
    main()
