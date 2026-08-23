import json
import glob
import os

def get_avg(file_path):
    if not os.path.exists(file_path): return 0.0
    scores = []
    with open(file_path) as f:
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                sc = data.get("correctness_score")
                if sc is not None:
                    scores.append(sc)
            except: pass
    return sum(scores)/len(scores) if scores else 0.0

models = [
    ("GPT-5.1", "openai_gpt-5.1"),
    ("Gemini 2.5", "google_gemini-2.5-pro"),
    ("Qwen 3-VL", "qwen_qwen3-vl-235b-a22b-instruct"),
    ("Qwen-Thinking", "qwen_qwen3-vl-235b-a22b-thinking")
]

print(f"{'Model':<15} | {'Baseline (No S2VA)':<20} | {'S2VA (Standard)':<20} | {'S2VA (Leaky)':<20} | {'Drop (Leaky)':<10}")
print("-" * 95)

for display_name, slug in models:
    # 1. Baseline RAG (False Text)
    # Note: baseline_rag path structure: results/{model}/baseline_rag/false_text.jsonl
    base_score = get_avg(f"results/{slug}/baseline_rag/false_text.jsonl")

    # 2. Standard S2VA (False Text)
    # Path: results/{model}/s2va/none/false_text.jsonl
    std_score = get_avg(f"results/{slug}/s2va/none/false_text.jsonl")

    # 3. Leaky S2VA (False Text)
    # Path: results/{model}/s2va_leaky/none/false_text.jsonl
    leaky_score = get_avg(f"results/{slug}/s2va_leaky/none/false_text.jsonl")

    drop = std_score - leaky_score
    
    print(f"{display_name:<15} | {base_score:.2%}               | {std_score:.2%}               | {leaky_score:.2%}               | {drop:+.2%}")

print("-" * 95)
