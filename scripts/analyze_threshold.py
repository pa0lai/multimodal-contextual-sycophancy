import json
import glob
import os
import matplotlib.pyplot as plt
import numpy as np

# 1. Build Case Mapping (ID -> Image Type)
case_map = {}
files = glob.glob("data/processed/**/*.json", recursive=True)
for f in files:
    try:
        d = json.load(open(f))
        case_map[str(d["id"])] = d.get("image_type", "unknown")
    except: pass

# 2. Load Scores
# Target: GPT-5.1, False Text, Abnormal Images (Most Critical)
MODEL = "openai_gpt-5.1"
CONDITION = "false_text"
TARGET_IMG_TYPE = "abnormal"

s2va_path = f"results/{MODEL}/s2va/none/{CONDITION}.jsonl"
base_path = f"results/{MODEL}/baseline_rag/{CONDITION}.jsonl"

def load_data(path):
    data_dict = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    cid = str(d["case_id"])
                    if case_map.get(cid) == TARGET_IMG_TYPE:
                        data_dict[cid] = d
                except: pass
    return data_dict

s2va_data = load_data(s2va_path)
base_data = load_data(base_path)

print(f"Loaded {len(s2va_data)} S2VA cases and {len(base_data)} Baseline cases (Abnormal).")

# 3. Simulate Thresholding
thresholds = np.arange(0.0, 1.01, 0.05) # 0 to 1.0 step 0.05
accuracies = []

for tau in thresholds:
    scores = []
    for cid, s_case in s2va_data.items():
        base_case = base_data.get(cid)
        if not base_case: continue # Should line up
        
        # Get witness confidence
        # Support both new "visual_confidence" and legacy "witness_confidence"
        conf = s_case.get("visual_confidence")
        if conf is None:
             conf = s_case.get("witness_confidence", 0.0)
        
        if conf >= tau:
            # S2VA is active
            sc = s_case.get("correctness_score")
            scores.append(sc if sc is not None else 0.0)
        else:
            # Fallback to Baseline (Context wins)
            sc = base_case.get("correctness_score")
            scores.append(sc if sc is not None else 0.0)

    avg_score = sum(scores) / len(scores) if scores else 0.0
    accuracies.append(avg_score)

# 4. Plot
plt.figure(figsize=(10, 6))
plt.plot(thresholds, accuracies, marker='o', linewidth=2, label='Simulated S2VA Accuracy')

# Add baseline horizontal line (Pure Baseline)
base_scores = [d.get("correctness_score") for d in base_data.values()]
base_scores = [s if s is not None else 0.0 for s in base_scores]
base_avg = sum(base_scores) / len(base_scores) if base_scores else 0.0
plt.axhline(y=base_avg, color='r', linestyle='--', label=f'Baseline RAG ({base_avg:.1%})')

# Add Pure S2VA horizontal line (Pure S2VA without threshold simulation - effectively tau=0)
s2va_scores = [d.get("correctness_score") for d in s2va_data.values()]
s2va_scores = [s if s is not None else 0.0 for s in s2va_scores]
s2va_avg = sum(s2va_scores) / len(s2va_scores) if s2va_scores else 0.0
plt.axhline(y=s2va_avg, color='g', linestyle='--', label=f'Standard S2VA ({s2va_avg:.1%})')

plt.title(f'Sensitivity Analysis: Witness Confidence Threshold (τ)\nGPT-5.1 on Abnormal Images w/ False Text')
plt.xlabel('Confidence Threshold (τ)')
plt.ylabel('Simulated Correctness Score')
plt.xticks(np.arange(0, 1.1, 0.1))
plt.ylim(0, 1.0)
plt.grid(True, alpha=0.3)
plt.legend()

for i, txt in enumerate(accuracies):
    if i % 2 == 0: # Annotate every other point
        plt.annotate(f"{txt:.2f}", (thresholds[i], txt), xytext=(0, 5), textcoords="offset points", ha='center', fontsize=8)

plt.savefig('threshold_sensitivity_gpt5.png')
print("Plot saved to threshold_sensitivity_gpt5.png")

# Print Sweet Spot
max_acc = max(accuracies)
best_tau = thresholds[accuracies.index(max_acc)]
print(f"Max Accuracy: {max_acc:.2%} at tau >= {best_tau:.2f}")
