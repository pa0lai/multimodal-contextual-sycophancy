from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from src.experiment.config import TestCase


DEFAULT_ROUTER_PATH = Path("results/router_artifacts/adaptive_router_minimal.json")
DEFAULT_ROUTER_DIR = Path("results/router_artifacts/by_model")


HEDGE_WORDS = {
    "maybe",
    "might",
    "seems",
    "seem",
    "appears",
    "appear",
    "likely",
    "probably",
    "uncertain",
    "unclear",
    "possibly",
    "perhaps",
    "may",
}


def count_hedges(text: str) -> float:
    tokens = [tok.strip(".,;:!?()[]{}\"'").lower() for tok in (text or "").split()]
    return float(sum(tok in HEDGE_WORDS for tok in tokens))


def slugify_model_name(model_name: str) -> str:
    return (model_name or "unknown").replace("/", "_")


@dataclass
class AdaptiveRouter:
    numeric_names: Tuple[str, ...]
    numeric_mean: Dict[str, float]
    numeric_std: Dict[str, float]
    weights: np.ndarray
    threshold: float
    threshold_accuracy: float = float("nan")
    cv_accuracy: float = float("nan")
    baseline_accuracy: float = float("nan")
    s2va_accuracy: float = float("nan")
    oracle_accuracy: float = float("nan")

    @classmethod
    def load(
        cls,
        path: Path | str = DEFAULT_ROUTER_PATH,
        model_name: Optional[str] = None,
        router_dir: Path | str = DEFAULT_ROUTER_DIR,
    ) -> Optional["AdaptiveRouter"]:
        candidates = []
        if model_name:
            slug = slugify_model_name(model_name)
            candidates.append(Path(router_dir) / f"adaptive_router_minimal_{slug}.json")
        candidates.append(Path(path))

        for candidate in candidates:
            candidate = Path(candidate)
            if not candidate.exists():
                continue
            with candidate.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            router = cls(
                numeric_names=tuple(data["numeric_names"]),
                numeric_mean={k: float(v) for k, v in data["numeric_mean"].items()},
                numeric_std={k: float(v) for k, v in data["numeric_std"].items()},
                weights=np.array(data["weights"], dtype=float),
                threshold=float(data.get("threshold", 0.5)),
                threshold_accuracy=float(data.get("threshold_accuracy", float("nan"))),
                cv_accuracy=float(data.get("cv_accuracy", float("nan"))),
                baseline_accuracy=float(data.get("baseline_accuracy", float("nan"))),
                s2va_accuracy=float(data.get("s2va_accuracy", float("nan"))),
                oracle_accuracy=float(data.get("oracle_accuracy", float("nan"))),
            )
            return router
        return None

    def _feature_dict(self, case: TestCase, witness_report: Dict[str, Any]) -> Dict[str, float]:
        report = witness_report.get("report", "") or ""
        confidence = witness_report.get("confidence", 0.0)
        return {
            "confidence": float(confidence),
            "witness_chars": float(len(report)),
            "witness_words": float(len(report.split())),
            "query_words": float(len((case.query or "").split())),
            "hedges": count_hedges(report),
            "abnormal": 1.0 if case.image_type == "abnormal" else 0.0,
        }

    def score(self, case: TestCase, witness_report: Dict[str, Any]) -> float:
        feats = self._feature_dict(case, witness_report)
        values = []
        for name in self.numeric_names:
            val = feats.get(name, 0.0)
            mean = self.numeric_mean.get(name, 0.0)
            std = self.numeric_std.get(name, 1.0) or 1.0
            values.append((val - mean) / std)
        x = np.array([1.0] + values, dtype=float)
        logits = float(np.dot(self.weights, x))
        logits = max(min(logits, 30.0), -30.0)
        return float(1.0 / (1.0 + np.exp(-logits)))

    def should_use_s2va(self, case: TestCase, witness_report: Dict[str, Any]) -> Tuple[bool, float]:
        prob = self.score(case, witness_report)
        return prob >= self.threshold, prob
