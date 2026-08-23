#!/usr/bin/env python3
"""Build sanitized metadata and compact results from the private archive.

This script is for release engineering. It never copies raw images, provider
responses, reasoning traces, or the private repository's Git history.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable


RELEASE_ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    "anthropic_claude-sonnet-4.5",
    "google_gemini-2.5-pro",
    "moonshotai_kimi-k2.5",
    "openai_gpt-5.1",
    "qwen_qwen3-vl-235b-a22b-instruct",
    "qwen_qwen3-vl-235b-a22b-thinking",
)
PUBLIC_RESULT_FIELDS = (
    "schema_version",
    "case_id",
    "image_type",
    "model_id",
    "experimental_phase",
    "text_condition",
    "attack_condition",
    "correctness_score",
    "common_sense_score",
    "text_faithfulness_score",
    "visual_faithfulness_score",
    "witness_confidence",
    "generator_source_split",
    "original_source",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_whitelist(archive: Path) -> None:
    for source in sorted((archive / "src").rglob("*.py")):
        relative = source.relative_to(archive)
        target = RELEASE_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    scripts = (
        "_bootstrap.py",
        "run_inference.py",
        "run_judge.py",
        "analyze_dose_response.py",
        "analyze_interaction.py",
        "analyze_leaky.py",
        "analyze_threshold.py",
        "analyze_universal.py",
        "analyze_witness_metrics.py",
        "compute_bootstrap_ci.py",
        "derive_witness_only.py",
    )
    for name in scripts:
        shutil.copy2(archive / "scripts" / name, RELEASE_ROOT / "scripts" / name)

    shutil.copy2(archive / "docs" / "ALL_PROMPTS.md", RELEASE_ROOT / "docs" / "ALL_PROMPTS.md")
    annotation_fields = {
        "judge_validation.csv": ["case_id", "image_path", "image_type", "model", "phase", "condition", "judge_score", "judge_agree", "human_correct", "error_type"],
        "true_context_audit.csv": ["case_id", "image_path", "visually_correct", "not_misleading", "answers_target", "usable_for_paradox"],
    }
    for name, fields in annotation_fields.items():
        source = archive / "annotations" / name
        target = RELEASE_ROOT / "annotations" / name
        with source.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    for source in sorted((archive / "figures").glob("*.png")):
        shutil.copy2(source, RELEASE_ROOT / "figures" / source.name)


def sanitized_case(record: dict[str, Any], split: str) -> dict[str, Any]:
    clean = dict(record)
    case_id = str(clean.get("id", clean.get("case_id", "")))
    image_type = str(clean.get("image_type", "unknown"))
    clean["id"] = case_id
    clean["image_type"] = image_type
    clean["image_path"] = f"data/raw_images/{image_type}/{case_id}.png"
    clean["generator_source_split"] = split
    metadata = dict(clean.get("metadata") or {})
    metadata.pop("source_path", None)
    source_dir = metadata.get("source_data_dir")
    if source_dir:
        metadata["source_data_dir"] = Path(str(source_dir)).as_posix().lstrip("/")
    clean["metadata"] = metadata
    return clean


def export_cases(archive: Path) -> tuple[dict[str, str], dict[str, str]]:
    full_map: dict[str, str] = {}
    heldout_map: dict[str, str] = {}
    case_exports = (
        (
            archive / "data" / "processed_v2",
            RELEASE_ROOT / "data" / "metadata" / "schema_v2_cases.jsonl",
            "gemini_generated",
            full_map,
        ),
        (
            archive / "data" / "non_gemini_heldout",
            RELEASE_ROOT / "data" / "metadata" / "gpt4o_regenerated_cases.jsonl",
            "gpt4o_regenerated",
            heldout_map,
        ),
    )
    for source_dir, output, split, image_map in case_exports:
        records = []
        for source in sorted(source_dir.glob("*/*.json"), key=lambda p: (p.parent.name, int(p.stem))):
            record = sanitized_case(json.loads(source.read_text(encoding="utf-8")), split)
            records.append(record)
            image_map[record["id"]] = record["image_type"]
        with output.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    heldout_manifest = json.loads((archive / "data" / "non_gemini_heldout" / "manifest.json").read_text())
    heldout_manifest["image_type_counts"] = {"abnormal": 100, "normal": 100}
    heldout_manifest["headline_population"] = {"image_type": "abnormal", "n": 100}
    heldout_manifest["schema_version"] = 1
    write_json(RELEASE_ROOT / "data" / "manifests" / "gpt4o_regenerated_subset.json", heldout_manifest)
    write_json(
        RELEASE_ROOT / "data" / "manifests" / "full_split.json",
        {
            "schema_version": 2,
            "generator_source_split": "gemini_generated",
            "evaluated_metadata_counts": {
                "abnormal": sum(value == "abnormal" for value in full_map.values()),
                "normal": sum(value == "normal" for value in full_map.values()),
                "total": len(full_map),
            },
            "source_image_pool_counts": {"abnormal_whoops": 499, "normal_imagenet_train": 500, "total": 999},
            "headline_population": {"image_type": "abnormal", "n": 499},
            "normal_case_500_status": "POST_PREPROCESSING_EXACT_RECOVERY_COMPLETE",
            "imagenet_exact_set_matches": 500,
            "imagenet_resolved_source_identities": 500,
        },
    )
    return full_map, heldout_map


def model_from_path(relative: Path, row: dict[str, Any]) -> str:
    explicit = row.get("model_name") or (row.get("metadata") or {}).get("model")
    if explicit:
        return str(explicit)
    slug = relative.parts[1]
    replacements = {
        "openai_gpt-5.1": "openai/gpt-5.1",
        "anthropic_claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
        "google_gemini-2.5-pro": "google/gemini-2.5-pro",
        "moonshotai_kimi-k2.5": "moonshotai/kimi-k2.5",
        "qwen_qwen3-vl-235b-a22b-instruct": "qwen/qwen3-vl-235b-a22b-instruct",
        "qwen_qwen3-vl-235b-a22b-thinking": "qwen/qwen3-vl-235b-a22b-thinking",
    }
    return replacements.get(slug, slug)


def canonical_sources(archive: Path) -> Iterable[tuple[Path, str, dict[str, str]]]:
    full_map = json.loads((RELEASE_ROOT / "tools" / ".full_map.json").read_text())
    heldout_map = json.loads((RELEASE_ROOT / "tools" / ".heldout_map.json").read_text())
    for model in MODELS:
        root = archive / "results" / model
        for source in sorted(root.rglob("*.jsonl")):
            relative = source.relative_to(archive)
            if any(" " in part for part in relative.parts):
                continue
            yield source, "gemini_generated", full_map
    for source in sorted((archive / "results_non_gemini").rglob("*.jsonl")):
        yield source, "gpt4o_regenerated", heldout_map


def export_results(archive: Path, full_map: dict[str, str], heldout_map: dict[str, str]) -> None:
    write_json(RELEASE_ROOT / "tools" / ".full_map.json", full_map)
    write_json(RELEASE_ROOT / "tools" / ".heldout_map.json", heldout_map)
    outputs = {
        "gemini_generated": RELEASE_ROOT / "results" / "compact" / "gemini_generated.jsonl",
        "gpt4o_regenerated": RELEASE_ROOT / "results" / "compact" / "gpt4o_regenerated.jsonl",
    }
    handles = {name: path.open("w", encoding="utf-8") for name, path in outputs.items()}
    manifest_sources = []
    try:
        for source, split, image_map in canonical_sources(archive):
            relative = source.relative_to(archive)
            row_count = 0
            seen_fields: set[str] = set()
            with source.open(encoding="utf-8") as input_handle:
                for line_number, line in enumerate(input_handle, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"Malformed JSON at {relative}:{line_number}") from error
                    case_id = str(row.get("case_id", ""))
                    if case_id not in image_map:
                        raise ValueError(f"No image_type mapping for {relative}:{line_number}, case {case_id}")
                    seen_fields.update(row)
                    compact = {
                        "schema_version": 1,
                        "case_id": case_id,
                        "image_type": image_map[case_id],
                        "model_id": model_from_path(relative, row),
                        "experimental_phase": row.get("inference_type"),
                        "text_condition": row.get("condition"),
                        "attack_condition": row.get("attack", "none"),
                        "correctness_score": row.get("correctness_score"),
                        "common_sense_score": row.get("common_sense_score"),
                        "text_faithfulness_score": row.get("text_faithfulness_score"),
                        "visual_faithfulness_score": row.get("visual_faithfulness_score"),
                        "witness_confidence": row.get("witness_confidence", row.get("visual_confidence")),
                        "generator_source_split": split,
                        "original_source": relative.as_posix(),
                    }
                    handles[split].write(json.dumps(compact, ensure_ascii=False) + "\n")
                    row_count += 1
            removed = sorted(seen_fields - {
                "case_id", "model_name", "inference_type", "condition", "attack",
                "correctness_score", "common_sense_score", "text_faithfulness_score",
                "visual_faithfulness_score", "witness_confidence", "visual_confidence",
            })
            manifest_sources.append(
                {
                    "original_relative_path": relative.as_posix(),
                    "byte_size": source.stat().st_size,
                    "sha256": sha256(source),
                    "row_count": row_count,
                    "compact_output_path": outputs[split].relative_to(RELEASE_ROOT).as_posix(),
                    "removed_field_count": len(removed),
                    "removed_field_categories": [
                        "model_generated_text", "reasoning_and_judge_metadata",
                        "query_or_reference_text", "provider_or_run_metadata",
                    ],
                    "reason_for_removal": "Data minimization: remove prompts, answers, reasoning, and provider metadata while retaining reported numeric metrics.",
                }
            )
    finally:
        for handle in handles.values():
            handle.close()
        (RELEASE_ROOT / "tools" / ".full_map.json").unlink(missing_ok=True)
        (RELEASE_ROOT / "tools" / ".heldout_map.json").unlink(missing_ok=True)

    write_json(
        RELEASE_ROOT / "results" / "manifest.json",
        {
            "schema_version": 1,
            "compact_schema_fields": list(PUBLIC_RESULT_FIELDS),
            "sources": manifest_sources,
        },
    )


def export_private_image_hashes(archive: Path) -> None:
    records = []
    for source in sorted((archive / "data" / "raw_images").glob("*/*.png")):
        records.append(
            {
                "private_archive_path": source.relative_to(archive).as_posix(),
                "byte_size": source.stat().st_size,
                "sha256": sha256(source),
            }
        )
    write_json(
        RELEASE_ROOT / "data" / "manifests" / "private_image_sha256.json",
        {
            "schema_version": 2,
            "contains_images": False,
            "source_counts": {"abnormal_whoops": 499, "normal_imagenet_train": 500},
            "mapping_status": {
                "abnormal": "RECOVERED_499_OF_499_IDENTITIES",
                "normal": "RECOVERED_500_OF_500_POST_PREPROCESSING_EXACT",
            },
            "files": records,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="Path to the private archival repository")
    args = parser.parse_args()
    archive = args.archive.resolve()
    if not (archive / ".git").exists():
        raise SystemExit("archive must be a Git working tree")
    copy_whitelist(archive)
    full_map, heldout_map = export_cases(archive)
    export_results(archive, full_map, heldout_map)
    export_private_image_hashes(archive)


if __name__ == "__main__":
    main()
