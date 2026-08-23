import json

import pytest

from src.experiment.config import TestCase as Case, is_portable_image_path, load_test_cases, resolve_context
from src.experiment.runner import parse_arbiter_response


def case(**updates):
    values = dict(id="1", image_path="data/raw_images/abnormal/1.png", query="q", visual_truth="v", true_text="true", false_text="strong", irrelevant_text="other", image_type="abnormal", weak_text="weak", medium_text="medium", strong_text="strong")
    values.update(updates)
    return Case(**values)


def test_load_schema_v1_and_v2(tmp_path):
    records = [
        {"id": "1", "image_path": "images/1.png", "query": "q", "ground_truth": "v", "true_text": "t", "false_text": "f", "irrelevant_text": "i", "image_type": "normal"},
        {"id": "2", "image_path": "images/2.png", "query": "q", "visual_truth": "v", "true_text": "t", "false_text": "f", "irrelevant_text": "i", "image_type": "abnormal", "schema_version": 2, "weak_text": "w"},
    ]
    for record in records:
        (tmp_path / f"{record['id']}.json").write_text(json.dumps(record))
    loaded = sorted(load_test_cases(str(tmp_path)), key=lambda item: item.id)
    assert [item.schema_version for item in loaded] == [1, 2]
    assert loaded[0].visual_truth == "v"
    assert loaded[1].weak_text == "w"


def test_load_jsonl(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"id": "3", "image_path": "images/3.png", "query": "q", "visual_truth": "v", "true_text": "t", "false_text": "f", "irrelevant_text": "i", "image_type": "abnormal", "schema_version": 2}) + "\n")
    assert [item.id for item in load_test_cases(str(path))] == ["3"]


@pytest.mark.parametrize("condition,expected", [("weak_text", "weak"), ("medium_text", "medium"), ("strong_text", "strong"), ("true_text", "true"), ("none", "")])
def test_context_resolution(condition, expected):
    assert resolve_context(case(), condition) == expected


def test_context_resolution_prefers_toxic_map():
    assert resolve_context(case(), "weak_text", {"1": {"weak_text": "mapped"}}) == "mapped"


@pytest.mark.parametrize("value", ["/" + "home/user/image.png", "/" + "Users/user/image.png", "C:" + r"\\Users\\user\\image.png"])
def test_absolute_image_paths_rejected(value, tmp_path):
    assert not is_portable_image_path(value)
    record = {"id": "1", "image_path": value, "query": "q", "visual_truth": "v", "true_text": "t", "false_text": "f", "irrelevant_text": "i", "image_type": "abnormal"}
    (tmp_path / "1.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="portable"):
        load_test_cases(str(tmp_path))


def test_arbiter_response_parsing():
    reasoning, answer = parse_arbiter_response("<think>compare evidence</think><answer>visual answer</answer>")
    assert reasoning == "compare evidence"
    assert answer == "visual answer"
