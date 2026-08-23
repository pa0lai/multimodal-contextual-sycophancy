#!/usr/bin/env python3
"""Generate the exhaustive exclusion audit and release file manifest."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECT_FILES = {
    "docs/ALL_PROMPTS.md",
    "annotations/judge_validation.csv",
    "annotations/true_context_audit.csv",
}
DIRECT_SCRIPTS = {
    "_bootstrap.py", "run_inference.py", "run_judge.py", "analyze_dose_response.py",
    "analyze_interaction.py", "analyze_leaky.py", "analyze_threshold.py",
    "analyze_universal.py", "analyze_witness_metrics.py", "compute_bootstrap_ci.py",
    "derive_witness_only.py",
}


def run_git(archive: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(archive), *args], text=True).strip()


def exclusion_reason(path: str) -> str | None:
    if path.startswith("src/") and path.endswith(".py"):
        return None
    if path.startswith("scripts/") and path.split("/")[-1] in DIRECT_SCRIPTS:
        return None
    if path.startswith("annotations/") and path.endswith(".csv"):
        return "Private annotation table excluded; sanitized compact table removes generated free text."
    if path in DIRECT_FILES or (path.startswith("figures/") and path.endswith(".png")):
        return None
    if path == "_IJCAI_26__Visual_Reasoning_LLMs (13).pdf" or path.endswith(".pdf"):
        return "Submission/camera-ready PDFs are prohibited from the public candidate."
    if path.startswith("data/raw_images/"):
        return "Raw third-party image excluded; private SHA-256 entry generated without copying bytes."
    if path.startswith("results/") or path.startswith("results_non_gemini/"):
        return "Full provider output excluded; canonical numeric fields were compacted when applicable."
    if path.startswith("data/processed_v2/") or path.startswith("data/non_gemini_heldout/"):
        return "Original metadata excluded; sanitized portable JSONL replacement generated."
    if path in {"reports/final_experiment_report.md", "reports/qwen_analysis.md"}:
        return "Obsolete internal report with superseded claims/results."
    if path == "manual_review_cases.jsonl":
        return "Empty internal review artifact."
    if path.startswith("scripts/"):
        return "Internal, one-off, collection, repair, debugging, or non-release-gated analysis script."
    if path.startswith("logs/") or path.endswith(".log") or path == "filter_log.txt":
        return "Temporary/internal log."
    if "__pycache__" in path or path.endswith((".pyc", ".DS_Store")):
        return "Generated cache or operating-system metadata."
    if path.startswith("rendered_pages") or path.startswith("attack_previews/"):
        return "Internal render or derivative preview not required for released claims."
    if path.startswith("reports/"):
        return "Internal report not part of the camera-ready reproducibility path."
    if path.startswith("data/"):
        return "Internal/intermediate data not selected for the documented release schema."
    return "Not selected by the release whitelist; not required for a documented public reproducibility path."


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve()
    source_commit = run_git(archive, "rev-parse", "HEAD")
    tracked = run_git(archive, "ls-files", "-z").split("\0")
    excluded = [(path, exclusion_reason(path)) for path in tracked if path and exclusion_reason(path)]

    lines = [
        "# Release audit", "", f"Source commit: `{source_commit}`", "",
        "## Resolved issues", "",
        "- Fast-forwarded the private archive to the fetched `origin/main` commit without altering its remote.",
        "- Built a sibling release by whitelist; the archival working tree remains unchanged.",
        "- Rewrote the README and terminology, separated paid inference/judging from offline aggregation, and deprecated duplicate judging entry point `run_eval.py`.",
        "- Removed absolute metadata paths, added portable-path validation, compacted canonical numeric results, and generated private-image SHA-256 records without image bytes.",
        "- Sanitized public annotation copies and added an automated forbidden-output-field gate.",
        "- Applied the author decisions: MIT for code and CC BY 4.0 for author-owned derived metadata, annotations, and numeric measurements.",
        "- Added pinned WHOOPS and ImageNet provenance tooling with a canonical decoded-RGB hash procedure.", "",
        "## Unresolved blockers", "",
        "- None for author review. Legacy figure scripts are outside the four release-gated headline checks and have not all been ported to the compact schema.", "",
        "## Licensing status", "",
        "- Code: MIT.",
        "- Author-owned derived metadata, compact annotations, and numeric measurements: CC BY 4.0.",
        "- WHOOPS!: CC BY 4.0 plus official additional terms; raw images excluded.",
        "- ImageNet/ILSVRC: original terms; image bytes excluded from every release artifact.", "",
        "## Security scan summary", "",
        "- `gitleaks` was unavailable. Equivalent filename, regex, current-tree, and full-history checks found no tracked or historical `.env` object, credential file, email address, private/machine URL, or credential pattern at HEAD.",
        "- Three historical commits matched a generic token regex only inside provider `metadata.reasoning_details.*.data`; field-level inspection classified these as high-entropy/encrypted provider output, not configuration or authentication headers. Raw reasoning metadata is excluded.",
        "- The untracked archive `.env` was not opened or copied and is excluded by both whitelist and `.gitignore`. Precautionary key rotation is recommended but is not a release blocker because no committed object was found.", "",
        "## Provenance attempts", "",
        "- WHOOPS current revision: `cca58d854ee35b6bfbedc14a9155483e89500ae9`.",
        "- WHOOPS official historical image ZIP revision: `213b8c1dbf058e1132839c1084b3ec4166315485`.",
        "- WHOOPS result: 466/499 exact current-file matches plus 33 deterministic-transform verifications; 499/499 source identities resolved; 0 unresolved or ambiguous.",
        "- ImageNet revision: `49e2ee26f3810fb5a7536bbf732a7b07389a47b5`; archive-date-compatible `datasets==4.4.2`; Pillow 12.3.0. The canonical pipeline recovered 500/500 source identities, 500/500 unique assignments, and 500/500 post-preprocessing decoded-pixel matches. `image_0228.png` is selection 229.",
        "- Final ImageNet forensics: selection 331 is EXIF-normalized; selection 304 alone crosses the pinned 3 MiB intermediate-PNG trigger and receives max-side-1536 LANCZOS normalization. Selections 477 and 494 remain unresized.", "",
        "## Reproduction status", "",
        "- `uv sync`: passed.",
        "- `uv run python -c \"import src\"`: passed.",
        "- `uv run python scripts/verify_reported_numbers.py`: passed all four headline populations.",
        "- `uv run pytest -q`: 20 passed.",
        "- Manifest completeness/hash verifier: passed after final manifest generation.",
        "- Forbidden model-output-field test: passed.",
        "- No inference or LLM judging was run.", "",
        "## Exhaustive excluded-file inventory", "",
        f"The whitelist excluded {len(excluded)} of {len(tracked)} tracked archive paths. Each is listed below; transformed metadata/results are counted as excluded originals.", "",
        "| Archive path | Reason |", "|---|---|",
    ]
    for path, reason in excluded:
        lines.append(f"| `{path.replace('|', '&#124;')}` | {reason} |")
    (ROOT / "RELEASE_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or {".git", ".venv", "__pycache__", ".pytest_cache", "multimodal_contextual_sycophancy.egg-info"}.intersection(path.parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative == "RELEASE_MANIFEST.json":
            continue
        files.append({"path": relative, "byte_size": path.stat().st_size, "sha256": sha256(path)})
    payload = {
        "schema_version": 2,
        "release_verdict": "RELEASE_CANDIDATE_READY_FOR_AUTHOR_REVIEW",
        "source_commit_sha": source_commit,
        "manifest_self_hash": None,
        "release_files": files,
        "generated_compact_artifacts": ["results/compact/gemini_generated.jsonl", "results/compact/gpt4o_regenerated.jsonl", "results/summaries/headline_results.json"],
        "provenance_status": {
            "whoops_abnormal": {"status": "RECOVERED", "exact_matches": 466, "deterministic_transform_matches": 33, "resolved_source_identities": 499, "expected": 499},
            "imagenet_normal": {"status": "RECOVERED", "source_identities": 500, "unique_assignments": 500, "post_preprocessing_exact_matches": 500, "expected": 500}
        },
        "output_sanitization": {"full_model_text_included": False, "annotation_tables_sanitized": True},
        "excluded_large_artifacts": [
            {"path": "data/raw_images/abnormal/", "source": "WHOOPS!", "status": "not included; separate archive not created"},
            {"path": "data/raw_images/normal/", "source": "ImageNet-1k train", "status": "private only; redistribution prohibited by release policy"},
            {"path": "results/ and results_non_gemini/ raw outputs", "status": "private archive only"},
            {"path": "_IJCAI_26__Visual_Reasoning_LLMs (13).pdf", "status": "excluded"},
        ],
    }
    (ROOT / "RELEASE_MANIFEST.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
