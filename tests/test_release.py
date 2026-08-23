import json
import re
import subprocess
import sys
import csv
from pathlib import Path

from src.evaluation.summary import aggregate_correctness, matching_rows


ROOT = Path(__file__).resolve().parents[1]


def line_count(path):
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def test_compact_result_row_counts_and_manifest():
    expected = {"gemini_generated.jsonl": 161948, "gpt4o_regenerated.jsonl": 2000}
    for name, count in expected.items():
        assert line_count(ROOT / "results" / "compact" / name) == count
    manifest = json.loads((ROOT / "results" / "manifest.json").read_text())
    by_output = {}
    for source in manifest["sources"]:
        by_output[source["compact_output_path"]] = by_output.get(source["compact_output_path"], 0) + source["row_count"]
    assert by_output["results/compact/gemini_generated.jsonl"] == expected["gemini_generated.jsonl"]
    assert by_output["results/compact/gpt4o_regenerated.jsonl"] == expected["gpt4o_regenerated.jsonl"]


def test_offline_metric_aggregation():
    rows = [{"image_type": "abnormal", "correctness_score": 1}, {"image_type": "normal", "correctness_score": 0}]
    assert aggregate_correctness(matching_rows(rows, image_type="abnormal")) == {"n": 1, "score_sum": 1.0, "mean": 1.0}


def test_four_camera_ready_headlines():
    subprocess.run([sys.executable, "scripts/verify_reported_numbers.py"], cwd=ROOT, check=True)
    payload = json.loads((ROOT / "results" / "summaries" / "headline_results.json").read_text())
    assert payload["all_passed"]
    assert [item["observed_n"] for item in payload["results"]] == [499, 499, 100, 100]


def test_no_absolute_machine_paths_in_released_text():
    unix_home = "/" + "home" + "/"
    mac_home = "/" + "Users" + "/"
    windows_home = r"[A-Za-z]:\\" + "Users" + r"\\"
    pattern = re.compile(re.escape(unix_home) + r"[^\s\"']+|" + re.escape(mac_home) + r"[^\s\"']+|" + windows_home)
    extensions = {".md", ".py", ".toml", ".json", ".jsonl", ".yml", ".yaml", ".cff", ".txt", ".csv", ".example"}
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or {".git", ".venv"}.intersection(path.parts) or path.suffix not in extensions:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_env_file_and_readme_script_references_exist():
    assert not (ROOT / ".env").exists()
    readme = (ROOT / "README.md").read_text()
    references = set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", readme))
    assert references
    assert [name for name in references if not (ROOT / "scripts" / name).is_file()] == []


def test_forbidden_model_output_fields_absent_from_public_structured_rows():
    forbidden = {"final_answer", "raw_response", "visual_testimony", "arbiter_reasoning", "judge_reasoning", "model_answer"}

    def keys(value):
        if isinstance(value, dict):
            yield from value.keys()
            for child in value.values():
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or {".git", ".venv", "__pycache__", ".pytest_cache"}.intersection(path.parts):
            continue
        if path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                fields = set(next(csv.reader(handle), []))
            if fields & forbidden:
                offenders.append(str(path.relative_to(ROOT)))
        elif path.suffix == ".json":
            if set(keys(json.loads(path.read_text(encoding="utf-8")))) & forbidden:
                offenders.append(str(path.relative_to(ROOT)))
        elif path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                if any(set(keys(json.loads(line))) & forbidden for line in handle if line.strip()):
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_code_repository_contains_no_raw_images():
    raw = ROOT / "data" / "raw_images"
    assert not raw.exists() or not any(raw.rglob("*"))


def test_provenance_status_is_specific():
    whoops = json.loads((ROOT / "data/manifests/whoops_mapping_status.json").read_text())
    imagenet = json.loads((ROOT / "data/manifests/imagenet_mapping_status.json").read_text())
    assert whoops["exact_decoded_pixel_matches"] == 466
    assert whoops["deterministic_transform_verified"] == 33
    assert whoops["resolved_source_identities"] == 499
    assert whoops["unmatched_case_ids"] == []
    assert whoops["status"] == "RECOVERED"
    assert imagenet["source_identities"] == 500
    assert imagenet["unique_assignments"] == 500
    assert imagenet["post_preprocessing_decoded_pixel_matches"] == 500
    assert imagenet["image_0228_verified_index"] == 229
    assert imagenet["resize_applied_selection_indices"] == [304]
    assert imagenet["exif_normalization_selection_indices"] == [331]
    assert imagenet["status"] == "RECOVERED"
    forensic = json.loads((ROOT / "data/manifests/imagenet_forensic_report.json").read_text())
    assert forensic["decision"] == "POST_DOCUMENTED_PREPROCESSING_EXACT_RECOVERY"
    assert [case["selection_index"] for case in forensic["cases"]] == [304, 331]
    assert forensic["cases"][0]["dimensions_identical_before_transform"] is False
    assert forensic["cases"][1]["transform_aligned_pixel_metrics"]["mse"] == 0.0

    rows = {int(row["canonical_selection_index"]): row for row in csv.DictReader(
        (ROOT / "data/manifests/imagenet_normal_manifest.csv").open(newline="", encoding="utf-8")
    )}
    assert rows[304]["historical_private_filename"] == "303.png"
    assert rows[304]["applied_resize"] == "true"
    assert rows[304]["reconstructed_decoded_rgb_sha256"] == rows[304]["archived_decoded_rgb_sha256"]
    assert rows[331]["historical_private_filename"] == "330.png"
    assert rows[331]["applied_exif_transform"] == "true"
    assert rows[331]["applied_resize"] == "false"
    assert rows[331]["reconstructed_decoded_rgb_sha256"] == rows[331]["archived_decoded_rgb_sha256"]
    assert rows[477]["applied_resize"] == "false"
    assert rows[494]["applied_resize"] == "false"
