import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional

from _bootstrap import REPO_ROOT  # noqa: F401
from src.experiment.config import load_test_cases_map


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _norm_answer(text: Optional[str]) -> str:
    text = (text or "").lower()
    text = re.sub(r"final answer\s*[:：]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _score(row: Dict[str, Any]) -> Optional[float]:
    value = row.get("correctness_score")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize_confidences(rows: Iterable[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    vals = []
    for row in rows:
        v = row.get("visual_confidence")
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
    if not vals:
        return {"mean": None, "median": None, "ge_085": None}
    return {
        "mean": mean(vals),
        "median": median(vals),
        "ge_085": sum(v >= 0.85 for v in vals) / len(vals),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze witness accuracy, confidence, and arbiter override frequency.")
    parser.add_argument("--data_dir", default="data/processed")
    parser.add_argument("--results_dir", default="results")
    parser.add_argument("--condition", default="false_text")
    parser.add_argument("--image_type", default="abnormal", choices=["abnormal", "normal", "all"])
    parser.add_argument("--output", default="results/witness_metrics.json")
    args = parser.parse_args()

    cases = load_test_cases_map(args.data_dir)
    allowed_ids = {
        cid
        for cid, case in cases.items()
        if args.image_type == "all" or case.image_type == args.image_type
    }

    results_root = Path(args.results_dir)
    model_dirs = [p for p in results_root.iterdir() if p.is_dir()]
    summary = {}

    for model_dir in sorted(model_dirs):
        witness_path = model_dir / "witness_only" / "none" / f"{args.condition}.jsonl"
        s2va_path = model_dir / "s2va" / "none" / f"{args.condition}.jsonl"
        if not witness_path.exists() and not s2va_path.exists():
            continue

        witness_rows = {str(r.get("case_id")): r for r in _read_jsonl(witness_path) if str(r.get("case_id")) in allowed_ids}
        s2va_rows = {str(r.get("case_id")): r for r in _read_jsonl(s2va_path) if str(r.get("case_id")) in allowed_ids}
        shared_ids = sorted(set(witness_rows) & set(s2va_rows), key=lambda x: int(x) if x.isdigit() else x)

        witness_scores = [_score(witness_rows[cid]) for cid in witness_rows]
        s2va_scores = [_score(s2va_rows[cid]) for cid in s2va_rows]
        witness_scores = [v for v in witness_scores if v is not None]
        s2va_scores = [v for v in s2va_scores if v is not None]

        answer_diff = 0
        score_diff = 0
        for cid in shared_ids:
            if _norm_answer(witness_rows[cid].get("final_answer")) != _norm_answer(s2va_rows[cid].get("final_answer")):
                answer_diff += 1
            ws = _score(witness_rows[cid])
            ss = _score(s2va_rows[cid])
            if ws is not None and ss is not None and ws != ss:
                score_diff += 1

        model_summary = {
            "model_slug": model_dir.name,
            "condition": args.condition,
            "image_type": args.image_type,
            "n_witness": len(witness_scores),
            "n_s2va": len(s2va_scores),
            "n_shared": len(shared_ids),
            "witness_accuracy": mean(witness_scores) if witness_scores else None,
            "s2va_accuracy": mean(s2va_scores) if s2va_scores else None,
            "answer_override_rate": answer_diff / len(shared_ids) if shared_ids else None,
            "score_change_rate": score_diff / len(shared_ids) if shared_ids else None,
            "witness_confidence": _summarize_confidences(witness_rows.values()),
            "s2va_witness_confidence": _summarize_confidences(s2va_rows.values()),
        }
        summary[model_dir.name] = model_summary

    output = {
        "data_dir": args.data_dir,
        "results_dir": args.results_dir,
        "condition": args.condition,
        "image_type": args.image_type,
        "models": summary,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
