import json
import glob
import os
import matplotlib.pyplot as plt
import numpy as np

# Build case map from processed_v2 (current data)
print("Building Case Mapping...")
case_map = {}
for path in ["data/processed_v2", "data/processed"]:
    files = glob.glob(os.path.join(path, "**/*.json"), recursive=True)
    if files:
        for f in files:
            try:
                d = json.load(open(f))
                case_map[str(d["id"])] = d.get("image_type", "unknown")
            except:
                pass
        break
print(f"Loaded {len(case_map)} cases.")


def get_avg(file_path, target_type):
    if not os.path.exists(file_path):
        return None
    scores = []
    with open(file_path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                sc = d.get("correctness_score")
                cid = str(d.get("case_id"))
                itype = case_map.get(cid)
                if sc is not None and itype == target_type:
                    scores.append(float(sc))
            except:
                pass
    return sum(scores) / len(scores) if scores else None


BLUE = "#1f77b4"
RED = "#d62728"

models = [
    ("GPT-5.1", "openai_gpt-5.1"),
    ("Gemini 2.5 Pro", "google_gemini-2.5-pro"),
    ("Qwen3-VL (Thinking)", "qwen_qwen3-vl-235b-a22b-thinking"),
    ("Qwen3-VL (Instruct)", "qwen_qwen3-vl-235b-a22b-instruct"),
    ("Claude Sonnet 4.5", "anthropic_claude-sonnet-4.5"),
    ("Kimi-K2.5", "moonshotai_kimi-k2.5"),
]

for display_name, slug in models:
    input_dir = f"results/{slug}"
    param_path = os.path.join(input_dir, "param_only.jsonl")
    rag_path = os.path.join(input_dir, "baseline_rag/true_text.jsonl")

    y_param_normal = get_avg(param_path, "normal")
    y_param_abnormal = get_avg(param_path, "abnormal")
    y_rag_normal = get_avg(rag_path, "normal")
    y_rag_abnormal = get_avg(rag_path, "abnormal")

    if any(v is None for v in [y_param_normal, y_param_abnormal, y_rag_normal, y_rag_abnormal]):
        print(f"WARNING: missing data for {display_name}, skipping.")
        continue

    print(f"\n--- {display_name} ---")
    print(f"Normal  | No Context: {y_param_normal:.2%}  Correct Context: {y_rag_normal:.2%}")
    print(f"Abnormal| No Context: {y_param_abnormal:.2%}  Correct Context: {y_rag_abnormal:.2%}")

    labels = ["Normal Image", "Abnormal Image"]
    param_means = [y_param_normal, y_param_abnormal]
    rag_means = [y_rag_normal, y_rag_abnormal]

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.plot(labels, param_means, marker="o", color=BLUE, linewidth=2.5,
            markersize=10, label="No Context (Param Only)")
    ax.plot(labels, rag_means, marker="x", color=RED, linewidth=2.5,
            markersize=10, linestyle="--", markeredgewidth=2.5,
            label="Correct Context (RAG)")

    ax.set_ylabel("Accuracy", fontsize=13)
    ax.set_title(f"Interaction Effect: {display_name}", fontsize=13)
    ax.set_ylim(0, 1.05)
    ax.tick_params(labelsize=12)
    ax.legend(fontsize=11, frameon=True, loc="upper right")
    ax.grid(True, linestyle=":", alpha=0.6)

    for i, txt in enumerate(param_means):
        ax.annotate(f"{txt:.1%}", (i, txt), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=11, color=BLUE)
    for i, txt in enumerate(rag_means):
        ax.annotate(f"{txt:.1%}", (i, txt), xytext=(0, -17),
                    textcoords="offset points", ha="center", fontsize=11, color=RED)

    plt.tight_layout()
    # Filename overrides to match LaTeX \includegraphics references
    _overrides = {
        "anthropic_claude-sonnet-4.5": "interaction_plot_claude-sonnet-4.5.png",
    }
    filename = _overrides.get(slug, f"interaction_plot_{slug.replace('_', '-')}.png")
    plt.savefig(filename, dpi=100)
    print(f"Saved {filename}")
    plt.close()
