#!/usr/bin/env python3
"""Universal-style analyses for S2VA.

This script focuses on three questions:
1) Extra conditions: do the extended context conditions on Anthropic behave
   in the expected order?
2) Susceptibility indicator: can a simple baseline-context gap predict S2VA gain?
3) Generalization / hierarchy: does that indicator generalize across models?

The script only uses existing results files, so it does not require any new
experiments.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

from _bootstrap import REPO_ROOT  # noqa: F401


def load_jsonl(path: Path) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows[str(obj.get("case_id"))] = obj
    return rows


def mean_or_nan(values: Sequence[float]) -> float:
    arr = np.array(list(values), dtype=float)
    return float(arr.mean()) if len(arr) else float("nan")


def pearsonr_safe(x: Sequence[float], y: Sequence[float]) -> float:
    x_arr = np.array(list(x), dtype=float)
    y_arr = np.array(list(y), dtype=float)
    if len(x_arr) < 2 or len(y_arr) < 2:
        return float("nan")
    sx = x_arr.std()
    sy = y_arr.std()
    if sx < 1e-12 or sy < 1e-12:
        return float("nan")
    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else float("nan")


def fit_ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    X_ = np.hstack([np.ones((X.shape[0], 1)), X])
    coef, *_ = np.linalg.lstsq(X_, y, rcond=None)
    return coef


def predict_ols(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    X_ = np.hstack([np.ones((X.shape[0], 1)), X])
    return X_ @ coef


def list_model_dirs(results_root: Path) -> List[Path]:
    dirs = []
    for path in sorted(results_root.iterdir()):
        if (path / "baseline_rag").is_dir() and (path / "s2va" / "none").is_dir():
            dirs.append(path)
    return dirs


def load_condition_pairs(model_dir: Path, condition: str) -> List[Dict[str, Any]]:
    base_path = model_dir / "baseline_rag" / f"{condition}.jsonl"
    s2va_path = model_dir / "s2va" / "none" / f"{condition}.jsonl"
    base = load_jsonl(base_path)
    s2va = load_jsonl(s2va_path)
    shared = sorted(set(base) & set(s2va))
    rows = []
    for case_id in shared:
        b = base[case_id]
        s = s2va[case_id]
        rows.append(
            {
                "case_id": case_id,
                "model_slug": model_dir.name,
                "model_name": s.get("model_name") or b.get("model_name") or model_dir.name.replace("_", "/"),
                "condition": condition,
                "baseline": float(b.get("correctness_score", 0.0) or 0.0),
                "s2va": float(s.get("correctness_score", 0.0) or 0.0),
                "baseline_raw": b,
                "s2va_raw": s,
            }
        )
    return rows


def infer_available_conditions(model_dir: Path) -> List[str]:
    baseline_dir = model_dir / "baseline_rag"
    conds = [p.stem for p in baseline_dir.glob("*.jsonl")]
    return sorted(set(conds))


def build_susceptibility_table(model_dir: Path) -> Dict[str, Dict[str, float]]:
    """Per-case susceptibility = mean(control scores) - false_text score."""
    false_rows = load_condition_pairs(model_dir, "false_text")
    controls = {}
    for cond in ["true_text", "irrelevant_text", "no_context"]:
        rows = load_condition_pairs(model_dir, cond)
        if rows:
            controls[cond] = {r["case_id"]: r["baseline"] for r in rows}

    table: Dict[str, Dict[str, float]] = {}
    for row in false_rows:
        cid = row["case_id"]
        control_scores = [scores[cid] for scores in controls.values() if cid in scores]
        if not control_scores:
            continue
        table[cid] = {
            "false": row["baseline"],
            "s2va_false": row["s2va"],
            "susceptibility": mean_or_nan(control_scores) - row["baseline"],
            "true_minus_false": controls.get("true_text", {}).get(cid, float("nan")) - row["baseline"]
            if cid in controls.get("true_text", {})
            else float("nan"),
            "irrelevant_minus_false": controls.get("irrelevant_text", {}).get(cid, float("nan")) - row["baseline"]
            if cid in controls.get("irrelevant_text", {})
            else float("nan"),
            "no_context_minus_false": controls.get("no_context", {}).get(cid, float("nan")) - row["baseline"]
            if cid in controls.get("no_context", {})
            else float("nan"),
        }
    return table


def build_strong_susceptibility_table(model_dir: Path) -> Dict[str, Dict[str, float]]:
    """A stronger score using multiple control gaps and within-model normalization.

    The idea is to reward cases where the baseline is stable on controls but
    weak on false_text, without relying on just one control condition.
    """
    false_rows = load_condition_pairs(model_dir, "false_text")
    controls = {}
    for cond in ["true_text", "irrelevant_text", "no_context", "correct_context", "shuffled_context"]:
        rows = load_condition_pairs(model_dir, cond)
        if rows:
            controls[cond] = {r["case_id"]: r["baseline"] for r in rows}

    table: Dict[str, Dict[str, float]] = {}
    for row in false_rows:
        cid = row["case_id"]
        gaps = []
        for cond, score_map in controls.items():
            if cid in score_map:
                gaps.append(score_map[cid] - row["baseline"])
        if not gaps:
            continue
        gaps_arr = np.array(gaps, dtype=float)
        mean_gap = float(gaps_arr.mean())
        std_gap = float(gaps_arr.std())
        strong = mean_gap / (std_gap + 1e-6)
        table[cid] = {
            "false": row["baseline"],
            "s2va_false": row["s2va"],
            "mean_gap": mean_gap,
            "std_gap": std_gap,
            "strong_score": strong,
            "n_controls": float(len(gaps)),
        }
    return table


def summarize_model_level(model_dir: Path, susceptibility: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    false_rows = load_condition_pairs(model_dir, "false_text")
    gain = []
    sus = []
    for row in false_rows:
        cid = row["case_id"]
        if cid not in susceptibility:
            continue
        sus.append(susceptibility[cid]["susceptibility"])
        gain.append(row["s2va"] - row["baseline"])
    return {
        "s2va_gain_mean": mean_or_nan(gain),
        "susceptibility_mean": mean_or_nan(sus),
        "corr": pearsonr_safe(sus, gain),
        "n": float(len(gain)),
    }


def build_pooled_gain_rows(model_dirs: Sequence[Path], conditions: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for model_dir in model_dirs:
        sus_table = build_susceptibility_table(model_dir)
        for cond in conditions:
            for pair in load_condition_pairs(model_dir, cond):
                cid = pair["case_id"]
                if cid not in sus_table:
                    continue
                rows.append(
                    {
                        "model_slug": pair["model_slug"],
                        "model_name": pair["model_name"],
                        "condition": cond,
                        "case_id": cid,
                        "gain": pair["s2va"] - pair["baseline"],
                        "susceptibility": sus_table[cid]["susceptibility"],
                        "true_gap": sus_table[cid]["true_minus_false"],
                        "irrelevant_gap": sus_table[cid]["irrelevant_minus_false"],
                        "no_context_gap": sus_table[cid]["no_context_minus_false"],
                        "baseline": pair["baseline"],
                    }
                )
    return rows


def design_matrix(
    rows: Sequence[Dict[str, Any]],
    feature_names: Sequence[str],
    include_model: bool,
    include_condition: bool,
) -> Tuple[np.ndarray, List[str]]:
    cols: List[np.ndarray] = []
    names: List[str] = []
    for feat in feature_names:
        cols.append(np.array([r[feat] for r in rows], dtype=float)[:, None])
        names.append(feat)

    if include_model:
        models = sorted({r["model_slug"] for r in rows})
        for m in models:
            cols.append(np.array([1.0 if r["model_slug"] == m else 0.0 for r in rows], dtype=float)[:, None])
            names.append(f"model:{m}")

    if include_condition:
        conds = sorted({r["condition"] for r in rows})
        for c in conds:
            cols.append(np.array([1.0 if r["condition"] == c else 0.0 for r in rows], dtype=float)[:, None])
            names.append(f"cond:{c}")

    if not cols:
        return np.zeros((len(rows), 0), dtype=float), names
    return np.hstack(cols), names


def summarize_regression(
    rows: Sequence[Dict[str, Any]],
    feature_names: Sequence[str],
    include_model: bool,
    include_condition: bool,
) -> Dict[str, Any]:
    y = np.array([r["gain"] for r in rows], dtype=float)
    X, names = design_matrix(rows, feature_names=feature_names, include_model=include_model, include_condition=include_condition)
    coef = fit_ols(X, y) if len(rows) else np.zeros(1)
    pred = predict_ols(X, coef) if len(rows) else np.zeros_like(y)
    out = {
        "r2": r2_score(y, pred) if len(rows) else float("nan"),
        "coef": {name: float(val) for name, val in zip(["intercept"] + names, coef)},
        "n": len(rows),
    }
    return out


def loomo(rows: Sequence[Dict[str, Any]], feature_names: Sequence[str]) -> Dict[str, Any]:
    models = sorted({r["model_slug"] for r in rows})
    per_model: Dict[str, Dict[str, float]] = {}
    y_all = np.array([r["gain"] for r in rows], dtype=float)
    for held_out in models:
        train = [r for r in rows if r["model_slug"] != held_out]
        test = [r for r in rows if r["model_slug"] == held_out]
        if not train or not test:
            continue
        X_train = np.array([[r[f] for f in feature_names] for r in train], dtype=float)
        y_train = np.array([r["gain"] for r in train], dtype=float)
        coef = fit_ols(X_train, y_train)
        X_test = np.array([[r[f] for f in feature_names] for r in test], dtype=float)
        y_test = np.array([r["gain"] for r in test], dtype=float)
        pred = predict_ols(X_test, coef)
        per_model[held_out] = {
            "r2": r2_score(y_test, pred),
            "corr": pearsonr_safe([r[feature_names[0]] for r in test], y_test),
            "n": float(len(test)),
        }
    all_pred = np.zeros_like(y_all)
    for held_out in models:
        train = [r for r in rows if r["model_slug"] != held_out]
        test_idx = [i for i, r in enumerate(rows) if r["model_slug"] == held_out]
        if not train or not test_idx:
            continue
        coef = fit_ols(np.array([[r[f] for f in feature_names] for r in train], dtype=float), np.array([r["gain"] for r in train], dtype=float))
        X_test = np.array([[rows[i][f] for f in feature_names] for i in test_idx], dtype=float)
        all_pred[test_idx] = predict_ols(X_test, coef)
    return {
        "overall_r2": r2_score(y_all, all_pred),
        "overall_corr": pearsonr_safe([r[feature_names[0]] for r in rows], [r["gain"] for r in rows]),
        "per_model": per_model,
        "n": len(rows),
    }


def plot_susceptibility_scatter(rows: Sequence[Dict[str, Any]], out_path: Path) -> None:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model_name"]].append(r)

    plt.figure(figsize=(9, 7))
    palette = plt.get_cmap("tab10")
    for idx, (model, ms) in enumerate(sorted(by_model.items())):
        xs = np.array([r["susceptibility"] for r in ms], dtype=float)
        ys = np.array([r["gain"] for r in ms], dtype=float)
        plt.scatter(xs, ys, s=12, alpha=0.35, color=palette(idx % 10), label=model)

    X = np.array([[r["susceptibility"]] for r in rows], dtype=float)
    y = np.array([r["gain"] for r in rows], dtype=float)
    coef = fit_ols(X, y)
    xs = np.linspace(float(np.min(X)), float(np.max(X)), 100)
    ys = coef[0] + coef[1] * xs
    plt.plot(xs, ys, color="black", linewidth=2, label=f"OLS fit (R²={r2_score(y, predict_ols(X, coef)):.2f})")
    plt.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    plt.axvline(0.0, color="gray", linestyle="--", linewidth=1)
    plt.xlabel("Susceptibility = mean(control scores) - baseline(false_text)")
    plt.ylabel("S2VA gain = S2VA - baseline")
    plt.title("Can baseline susceptibility predict S2VA benefit?")
    plt.legend(fontsize=8, frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_anthropic_conditions(model_dir: Path, out_path: Path) -> List[Dict[str, Any]]:
    rows = []
    conditions = ["true_text", "false_text", "irrelevant_text", "no_context", "correct_context", "shuffled_context"]
    for cond in conditions:
        pairs = load_condition_pairs(model_dir, cond)
        if not pairs:
            continue
        rows.append(
            {
                "condition": cond,
                "baseline": mean_or_nan([p["baseline"] for p in pairs]),
                "s2va": mean_or_nan([p["s2va"] for p in pairs]),
                "gain": mean_or_nan([p["s2va"] - p["baseline"] for p in pairs]),
                "n": len(pairs),
            }
        )

    if not rows:
        return rows

    rows_sorted = rows
    xs = np.arange(len(rows_sorted))
    width = 0.36
    plt.figure(figsize=(11, 5))
    plt.bar(xs - width / 2, [r["baseline"] for r in rows_sorted], width=width, label="Baseline", color="#4C78A8")
    plt.bar(xs + width / 2, [r["s2va"] for r in rows_sorted], width=width, label="S2VA", color="#F58518")
    plt.xticks(xs, [r["condition"] for r in rows_sorted], rotation=25, ha="right")
    plt.ylim(0, 1)
    plt.ylabel("Accuracy")
    plt.title("Anthropic: extended context conditions")
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()
    return rows


def sweep_adaptive_policy(
    rows: Sequence[Dict[str, Any]],
    score_key: str,
    threshold_grid: Sequence[float],
) -> Dict[str, Any]:
    if not rows:
        return {"best_threshold": float("nan"), "best_accuracy": float("nan"), "baseline": float("nan"), "s2va": float("nan"), "curve": []}
    baseline = mean_or_nan([r["baseline"] for r in rows])
    s2va = mean_or_nan([r["s2va"] for r in rows])
    curve = []
    best = (-1.0, float("nan"))
    for tau in threshold_grid:
        chosen = []
        for r in rows:
            chosen.append(r["s2va"] if r[score_key] >= tau else r["baseline"])
        acc = float(np.mean(chosen))
        curve.append({"tau": float(tau), "accuracy": acc})
        if acc > best[0]:
            best = (acc, float(tau))
    return {
        "best_threshold": best[1],
        "best_accuracy": best[0],
        "baseline": baseline,
        "s2va": s2va,
        "curve": curve,
    }


def plot_adaptive_curve(curve: Sequence[Dict[str, Any]], baseline: float, s2va: float, out_path: Path, title: str) -> None:
    if not curve:
        return
    xs = [c["tau"] for c in curve]
    ys = [c["accuracy"] for c in curve]
    plt.figure(figsize=(9, 5))
    plt.plot(xs, ys, marker="o", linewidth=2, color="#8884d8", label="Adaptive S2VA")
    plt.axhline(y=baseline, color="#ff7300", linestyle="--", label=f"Baseline ({baseline:.1%})")
    plt.axhline(y=s2va, color="#82ca9d", linestyle="--", label=f"Pure S2VA ({s2va:.1%})")
    plt.xlabel("Strong susceptibility threshold")
    plt.ylabel("Accuracy")
    plt.title(title)
    plt.grid(True, alpha=0.25)
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal-style analyses for S2VA.")
    parser.add_argument("--results_dir", default="results", help="Root results directory.")
    parser.add_argument("--out_dir", default="results/universal_analysis", help="Output directory for plots and summaries.")
    args = parser.parse_args()

    results_root = Path(args.results_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_dirs = list_model_dirs(results_root)
    if not model_dirs:
        raise SystemExit("No model result directories found.")

    # 1) Model-level susceptibility summaries from false_text.
    model_summaries: Dict[str, Dict[str, float]] = {}
    for model_dir in model_dirs:
        sus_table = build_susceptibility_table(model_dir)
        model_summaries[model_dir.name] = summarize_model_level(model_dir, sus_table)

    # 2) Pooled rows for common conditions across all models.
    pooled_rows = build_pooled_gain_rows(model_dirs, ["true_text", "false_text", "irrelevant_text"])

    # 3) Anthropics extra conditions.
    anthropic_dir = next((p for p in model_dirs if p.name == "anthropic_claude-sonnet-4.5"), None)
    anthropic_rows: List[Dict[str, Any]] = []
    if anthropic_dir is not None:
        anthropic_rows = plot_anthropic_conditions(anthropic_dir, out_dir / "anthropic_extended_conditions.png")

    # Regression summaries.
    reg_intercept = summarize_regression(pooled_rows, feature_names=[], include_model=False, include_condition=False)
    reg_sus1 = summarize_regression(pooled_rows, feature_names=["susceptibility"], include_model=False, include_condition=False)
    reg_sus2 = summarize_regression(
        pooled_rows,
        feature_names=["true_gap", "irrelevant_gap"],
        include_model=False,
        include_condition=False,
    )
    reg_model = summarize_regression(pooled_rows, feature_names=[], include_model=True, include_condition=False)
    reg_cond = summarize_regression(pooled_rows, feature_names=[], include_model=False, include_condition=True)
    reg_all = summarize_regression(
        pooled_rows,
        feature_names=["true_gap", "irrelevant_gap"],
        include_model=True,
        include_condition=True,
    )

    # Susceptibility LOOMO on false_text only.
    false_rows: List[Dict[str, Any]] = []
    strong_rows: List[Dict[str, Any]] = []
    for model_dir in model_dirs:
        sus_table = build_susceptibility_table(model_dir)
        strong_table = build_strong_susceptibility_table(model_dir)
        for cid, item in sus_table.items():
            false_rows.append(
                {
                    "model_slug": model_dir.name,
                    "model_name": model_dir.name.replace("_", "/"),
                    "case_id": cid,
                    "susceptibility": item["susceptibility"],
                    "true_gap": item["true_minus_false"],
                    "irrelevant_gap": item["irrelevant_minus_false"],
                    "gain": item["s2va_false"] - item["false"],
                }
            )
        for cid, item in strong_table.items():
            strong_rows.append(
                {
                    "model_slug": model_dir.name,
                    "model_name": model_dir.name.replace("_", "/"),
                    "case_id": cid,
                    "baseline": item["false"],
                    "s2va": item["s2va_false"],
                    "strong_score": item["strong_score"],
                    "mean_gap": item["mean_gap"],
                    "std_gap": item["std_gap"],
                    "gain": item["s2va_false"] - item["false"],
                }
            )

    loom1 = loomo(false_rows, feature_names=["susceptibility"])
    loom2 = loomo(false_rows, feature_names=["true_gap", "irrelevant_gap"])
    plot_susceptibility_scatter(false_rows, out_dir / "susceptibility_vs_gain.png")
    strong_curve = sweep_adaptive_policy(
        strong_rows,
        score_key="strong_score",
        threshold_grid=np.linspace(-2.0, 3.0, 26),
    )
    plot_adaptive_curve(
        strong_curve["curve"],
        baseline=strong_curve["baseline"],
        s2va=strong_curve["s2va"],
        out_path=out_dir / "adaptive_strong_score.png",
        title="Adaptive S2VA via strong susceptibility score",
    )

    # Print summary.
    print("\n=== Model-level susceptibility summary (false_text) ===")
    for model, vals in sorted(model_summaries.items()):
        print(
            f"{model:<34} sus={vals['susceptibility_mean']:.3f}  "
            f"gain={vals['s2va_gain_mean']:.3f}  corr={vals['corr']:.3f}  n={int(vals['n'])}"
        )

    print("\n=== Pooled regression on common conditions (true/false/irrelevant) ===")
    print(f"Intercept only R²: {reg_intercept['r2']:.3f}")
    print(f"+ susceptibility (1d) R²: {reg_sus1['r2']:.3f}")
    print(f"+ susceptibility (2d) R²: {reg_sus2['r2']:.3f}")
    print(f"+ model dummies R²: {reg_model['r2']:.3f}")
    print(f"+ condition dummies R²: {reg_cond['r2']:.3f}")
    print(f"+ susceptibility + model + condition R²: {reg_all['r2']:.3f}")
    print("Top coefficients (all):")
    coef_all = reg_all["coef"]
    for name, val in sorted(coef_all.items(), key=lambda kv: abs(kv[1]), reverse=True)[:12]:
        print(f"  {name:<25} {val:+.4f}")

    print("\n=== Leave-one-model-out on false_text gain ===")
    print(f"Overall LOOM R² (1d): {loom1['overall_r2']:.3f}")
    print(f"Overall corr (1d):    {loom1['overall_corr']:.3f}")
    print(f"Overall LOOM R² (2d): {loom2['overall_r2']:.3f}")
    print(f"Overall corr (2d):    {loom2['overall_corr']:.3f}")
    for model, vals in sorted(loom2["per_model"].items()):
        print(f"  {model:<34} R²={vals['r2']:.3f} corr={vals['corr']:.3f} n={int(vals['n'])}")

    print("\n=== Strong susceptibility adaptive policy ===")
    print(f"Baseline:      {strong_curve['baseline']:.3f}")
    print(f"Pure S2VA:     {strong_curve['s2va']:.3f}")
    print(f"Best threshold: {strong_curve['best_threshold']:.2f}")
    print(f"Best accuracy:  {strong_curve['best_accuracy']:.3f}")

    if anthropic_rows:
        print("\n=== Anthropic extra conditions ===")
        for row in anthropic_rows:
            print(
                f"{row['condition']:<18} baseline={row['baseline']:.3f} "
                f"s2va={row['s2va']:.3f} gain={row['gain']:+.3f} n={row['n']}"
            )

    summary = {
        "model_summaries": model_summaries,
        "pooled_rows": len(pooled_rows),
        "regressions": {
            "intercept": reg_intercept,
            "susceptibility_1d": reg_sus1,
            "susceptibility_2d": reg_sus2,
            "model": reg_model,
            "condition": reg_cond,
            "all": reg_all,
        },
        "loom_1d": loom1,
        "loom_2d": loom2,
        "strong_adaptive": strong_curve,
        "anthropic_extended_conditions": anthropic_rows,
        "outputs": {
            "susceptibility_scatter": str(out_dir / "susceptibility_vs_gain.png"),
            "anthropic_conditions": str(out_dir / "anthropic_extended_conditions.png"),
            "adaptive_strong_score": str(out_dir / "adaptive_strong_score.png"),
        },
    }
    out_json = out_dir / "universal_analysis.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved summary to {out_json}")


if __name__ == "__main__":
    main()
