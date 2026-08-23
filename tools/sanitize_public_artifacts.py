#!/usr/bin/env python3
"""Create compact public annotation tables without model-generated text."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEEP = {
    "judge_validation.csv": ["case_id", "image_path", "image_type", "model", "phase", "condition", "judge_score", "judge_agree", "human_correct", "error_type"],
    "true_context_audit.csv": ["case_id", "image_path", "visually_correct", "not_misleading", "answers_target", "usable_for_paradox"],
}


def main() -> None:
    for name, fields in KEEP.items():
        path = ROOT / "annotations" / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
        print(f"sanitized={path.relative_to(ROOT)} rows={len(rows)}")
    manifest_path = ROOT / "results" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        removed = source.pop("fields_removed", [])
        source["removed_field_count"] = len(removed)
        source["removed_field_categories"] = [
            "model_generated_text",
            "reasoning_and_judge_metadata",
            "query_or_reference_text",
            "provider_or_run_metadata",
        ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("sanitized=results/manifest.json removed_field_names=redacted")


if __name__ == "__main__":
    main()
