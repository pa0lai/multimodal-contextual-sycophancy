import json
import glob
import os
import matplotlib.pyplot as plt
import numpy as np

# 1. Build Case Mapping
case_map = {}
files = glob.glob("data/processed/**/*.json", recursive=True)
for f in files:
    try:
        d = json.load(open(f))
        case_map[str(d["id"])] = d.get("image_type", "unknown")
    except: pass

def get_avg(file_path, target_type="abnormal"):
    if not os.path.exists(file_path): return 0.0
    scores = []
    with open(file_path) as f:
        for line in f:
            if not line.strip(): continue
            try:
                d = json.loads(line)
                sc = d.get("correctness_score")
                cid = str(d.get("case_id"))
                itype = case_map.get(cid)
                if sc is not None and itype == target_type:
                    scores.append(sc)
            except: pass
    return sum(scores)/len(scores) if scores else 0.0

MODEL = "openai_gpt-5.1"
print(f"Analyzing Dose-Response for {MODEL} (Abnormal Cases)...")

# Data Points
levels = ["Weak", "Medium", "Strong"]
x_pos = np.arange(len(levels))

# Baseline RAG Scores
weak_score = get_avg(f"results/{MODEL}/dose_response/none/weak_text.jsonl")
medium_score = get_avg(f"results/{MODEL}/dose_response/none/medium_text.jsonl")
strong_score = get_avg(f"results/{MODEL}/dose_response/none/strong_text.jsonl")
if strong_score == 0.0:
    strong_score = get_avg(f"results/{MODEL}/baseline_rag/false_text.jsonl")  # Backward compatibility

accuracies = [weak_score, medium_score, strong_score]

print("\n--- Dose-Response Results ---")
print(f"Weak Text:   {weak_score:.2%}")
print(f"Medium Text: {medium_score:.2%}")
print(f"Strong Text: {strong_score:.2%}")

# S2VA reference line
s2va_strong = get_avg(f"results/{MODEL}/s2va/none/strong_text.jsonl")
if s2va_strong == 0.0:
    s2va_strong = get_avg(f"results/{MODEL}/s2va/none/false_text.jsonl")
print(f"S2VA (Strong): {s2va_strong:.2%}")

# Plotting
fig, ax = plt.subplots(figsize=(8, 6))

ax.plot(levels, accuracies, marker='o', linewidth=3, markersize=10, label='Baseline RAG', color='tab:red')
ax.axhline(y=s2va_strong, color='tab:green', linestyle='--', linewidth=2, label=f'S2VA (Strong Context) = {s2va_strong:.1%}')

ax.set_title(f'Dose-Response: Toxic Text Intensity vs Accuracy\n(GPT-5.1 on Abnormal Images)')
ax.set_xlabel('Interference Strength (Text Toxicity)')
ax.set_ylabel('Accuracy')
ax.set_ylim(0, 1.0)
ax.grid(True, linestyle=':', alpha=0.6)
ax.legend()

# Annotate
for i, txt in enumerate(accuracies):
    ax.annotate(f"{txt:.1%}", (i, txt), xytext=(0, 10), textcoords='offset points', ha='center', fontweight='bold')

plt.tight_layout()
plt.savefig('dose_response_gpt5.png')
print("\nPlot saved to dose_response_gpt5.png")
