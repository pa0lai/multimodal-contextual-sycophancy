from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

FILTER_FIELDS = ("generator_source_split", "image_type", "model_id", "experimental_phase", "text_condition", "attack_condition")


def load_compact_rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"Malformed JSON at {path}:{line_number}") from error
    return rows


def matching_rows(rows: Iterable[dict[str, Any]], **filters: str) -> list[dict[str, Any]]:
    unknown = set(filters) - set(FILTER_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported filters: {sorted(unknown)}")
    return [row for row in rows if all(row.get(key) == value for key, value in filters.items())]


def aggregate_correctness(rows: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    selected = list(rows)
    if not selected:
        raise ValueError("No compact rows matched the requested population")
    scores = [row.get("correctness_score") for row in selected]
    if any(not isinstance(score, (int, float)) for score in scores):
        raise ValueError("Matched rows contain a missing or non-numeric correctness_score")
    total = float(sum(scores))
    return {"n": len(scores), "score_sum": total, "mean": total / len(scores)}

