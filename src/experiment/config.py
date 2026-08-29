from dataclasses import dataclass, field
import glob
import json
import os
from pathlib import Path, PureWindowsPath
from typing import List, Optional, Dict, Any, Tuple

@dataclass
class TestCase:
    id: str
    image_path: str
    query: str
    visual_truth: str
    true_text: str
    false_text: str
    irrelevant_text: str
    image_type: str # 'normal' or 'abnormal'
    schema_version: int = 1
    no_context: str = ""
    correct_context: str = ""
    shuffled_context: str = ""
    weak_text: str = ""
    medium_text: str = ""
    strong_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExperimentResult:
    case_id: str
    model_name: str
    inference_type: str # 'param_only', 'baseline_rag', 's2va'
    query: str
    condition: str # 'true_text', 'false_text', 'irrelevant_text', 'no_text'
    blur_level: float
    
    # Outputs
    raw_response: str
    final_answer: str
    
    # S2VA specific
    visual_testimony: Optional[str] = None
    visual_confidence: Optional[float] = None
    
    # Evaluation
    correctness_score: float = 0.0
    common_sense_score: float = 0.0
    text_faithfulness_score: float = 0.0
    visual_faithfulness_score: float = 0.0
    
    metadata: Dict[str, Any] = field(default_factory=dict)

# Visual Attack Configurations
VISUAL_ATTACKS = [
    "none",
    "low_light_severe",
    "overexposure_severe",
    "compression_severe",
    "pixelation_severe",
    "rain_severe",
    "snow_severe",
    "spatter_severe"
]

# Backward-compatible blur presets used by older scripts.
BLUR_LEVELS = {
    "clear": 0.0,
    "mild": 1.5,
    "severe": 4.0,
}

SUPPORTED_PHASES = (
    "param_only",
    "baseline_rag",
    "baseline_rag_strong_visual",
    "baseline_rag_ignore_context",
    "s2va",
    "cot_rag",
    "evidence_separation",
    "cove_style_verification",
    "s2va_leaky",
    "visual_supremacy_only",
    "witness_only",
    "dose_response",
    "adaptive_s2va",
    "two_call_rag",
    "caption_then_rag",
)

LEGACY_TEXT_CONDITIONS = {
    "true_text",
    "false_text",
    "irrelevant_text",
}

EXTENDED_TEXT_CONDITIONS = {
    "no_context",
    "correct_context",
    "shuffled_context",
    "weak_text",
    "medium_text",
    "strong_text",
}


def is_portable_image_path(image_path: str) -> bool:
    """Return True for repository-relative image paths or stable logical IDs."""
    return bool(image_path) and "\x00" not in image_path and not Path(image_path).is_absolute() and not PureWindowsPath(image_path).is_absolute()


def validate_image_path(image_path: str) -> str:
    if not is_portable_image_path(image_path):
        raise ValueError(f"image_path must be portable and relative: {image_path!r}")
    return image_path


def _strip_leading_context_prefix(text: str) -> str:
    text = (text or "").strip()
    lowered = text.lower()
    prefixes = [
        "in this image,",
        "this picture shows",
        "this image shows",
        "in the image,",
    ]
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip(" ,.")
    return text


def derive_weak_context(strong_text: str) -> Tuple[str, str]:
    """Create weaker paraphrases from a strong false context."""
    base = _strip_leading_context_prefix(strong_text)
    if not base:
        return "", ""
    weak = f"It seems like {base[0].lower() + base[1:] if len(base) > 1 else base}"
    medium = f"It looks like {base}"
    return weak, medium


def resolve_context(
    case: TestCase,
    condition: Optional[str],
    toxic_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Resolve a text condition into the actual context string to feed the model."""
    if not condition or condition == "none":
        return ""

    if condition in {"none", "no_context"}:
        return ""

    if condition in {"true_text", "correct_context"}:
        return case.true_text or case.correct_context or ""

    if condition in {"false_text", "strong_text"}:
        return case.false_text or case.strong_text or ""

    if condition == "irrelevant_text":
        return case.irrelevant_text or ""

    if condition == "shuffled_context":
        return case.shuffled_context or ""

    if condition in {"weak_text", "medium_text"}:
        if toxic_map and str(case.id) in toxic_map:
            return toxic_map[str(case.id)].get(condition, "") or ""
        return getattr(case, condition, "") or ""

    return getattr(case, condition, "") or ""


def get_conditions_for_phase(phase: str, include_extended: bool = True) -> List[str]:
    """Return the text conditions to run for a phase."""
    if phase == "param_only":
        return ["none"]

    if phase == "dose_response":
        return ["weak_text", "medium_text", "strong_text"]

    if phase == "s2va_leaky":
        return ["false_text", "shuffled_context"]

    if phase in {
        "two_call_rag",
        "caption_then_rag",
        "baseline_rag_strong_visual",
        "baseline_rag_ignore_context",
        "evidence_separation",
        "cove_style_verification",
    }:
        return ["false_text", "true_text", "irrelevant_text"]

    if phase in {"visual_supremacy_only", "witness_only"}:
        base = ["true_text", "false_text", "irrelevant_text"]
        if include_extended:
            base.extend(["no_context", "correct_context", "shuffled_context"])
        return base

    if phase == "adaptive_s2va":
        base = ["true_text", "false_text", "irrelevant_text"]
        if include_extended:
            base.extend(["no_context", "correct_context", "shuffled_context"])
        return base

    base = ["true_text", "false_text", "irrelevant_text"]
    if include_extended:
        base.extend(["no_context", "correct_context", "shuffled_context"])
    return base


def load_test_cases(data_dir: str) -> List[TestCase]:
    """Load test cases from a directory, one JSON file, or one JSONL file."""
    cases: List[TestCase] = []
    source = Path(data_dir)
    records: List[Tuple[Dict[str, Any], str]] = []
    if source.is_file() and source.suffix == ".jsonl":
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    records.append((json.loads(line), f"{source.name}:{line_number}"))
    else:
        json_files = [str(source)] if source.is_file() else glob.glob(os.path.join(data_dir, "**/*.json"), recursive=True)
        for fpath in json_files:
            try:
                with open(fpath, "r", encoding="utf-8") as handle:
                    records.append((json.load(handle), os.path.basename(fpath)))
            except (OSError, json.JSONDecodeError):
                continue

    for data, source_label in records:

        visual_truth = data.get("visual_truth", data.get("ground_truth", ""))
        image_path = validate_image_path(data.get("image_path", ""))
        cases.append(
            TestCase(
                id=data.get("id", source_label),
                image_path=image_path,
                query=data.get("query", ""),
                visual_truth=visual_truth,
                true_text=data.get("true_text", ""),
                false_text=data.get("false_text", ""),
                irrelevant_text=data.get("irrelevant_text", ""),
                image_type=data.get("image_type", "unknown"),
                schema_version=int(data.get("schema_version", 1) or 1),
                no_context=data.get("no_context", ""),
                correct_context=data.get("correct_context", data.get("true_text", "")),
                shuffled_context=data.get("shuffled_context", ""),
                weak_text=data.get("weak_text", ""),
                medium_text=data.get("medium_text", ""),
                strong_text=data.get("strong_text", data.get("false_text", "")),
                metadata=data.get("metadata", {}),
            )
        )

    return cases


def load_test_cases_map(data_dir: str) -> Dict[str, TestCase]:
    """Load cases and map them by case ID."""
    return {str(case.id): case for case in load_test_cases(data_dir)}
