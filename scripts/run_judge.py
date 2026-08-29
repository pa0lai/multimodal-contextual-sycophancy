import argparse
import os
import glob

from _bootstrap import REPO_ROOT  # noqa: F401
from src.evaluation.evaluator import Evaluator

def main():
    parser = argparse.ArgumentParser(description="Run S2VA Evaluation (Judge)")
    parser.add_argument("--data_dir", type=str, default="data/processed", help="Directory containing original test case JSONs")
    parser.add_argument("--results_dir", type=str, default="results", help="Directory containing inference results (JSONL)")
    parser.add_argument("--models", type=str, nargs="+", default=None, help="Specific models to evaluate (e.g., openai/gpt-5.1)")
    parser.add_argument("--judge_model", type=str, default="openai/gpt-4o", help="Model to use for judging")
    parser.add_argument(
        "--phases",
        type=str,
        nargs="+",
        default=["param_only", "baseline_rag", "s2va", "cot_rag"],
        choices=[
            "param_only",
            "baseline_rag",
            "s2va",
            "cot_rag",
            "adaptive_s2va",
            "s2va_leaky",
            "visual_supremacy_only",
            "witness_only",
            "dose_response",
            "two_call_rag",
            "caption_then_rag",
        ],
        help="Phases to evaluate",
    )
    parser.add_argument("--max_workers", type=int, default=30, help="Number of parallel threads for judging")
    args = parser.parse_args()

    evaluator = Evaluator(data_dir=args.data_dir, output_dir=args.results_dir, judge_model=args.judge_model)
    
    print(f"Starting evaluation...")
    print(f"Data Source: {args.data_dir}")
    print(f"Results Source: {args.results_dir}")
    print(f"Phases to evaluate: {args.phases}")
    
    # Find all .jsonl files in results_dir (recursive)
    # Exclude already evaluated files (*_evaluated.jsonl)
    evaluator = Evaluator(data_dir=args.data_dir, output_dir=args.results_dir, judge_model=args.judge_model)
    
    # Recursively find all .jsonl files in the results directory
    all_jsonl_files = glob.glob(os.path.join(args.results_dir, "**/*.jsonl"), recursive=True)
    
    # Filter files based on phases and models
    files_to_evaluate = []
    model_slugs = [m.replace("/", "_") for m in args.models] if args.models else None
    
    for fpath in all_jsonl_files:
        # Check phase
        phase_match = any(f"/{phase}/" in fpath or f"/{phase}.jsonl" in fpath for phase in args.phases)
        # Check model
        model_match = True
        if model_slugs:
            model_match = any(slug in fpath for slug in model_slugs)
            
        if phase_match and model_match:
            files_to_evaluate.append(fpath)
    
    print(f"Found {len(files_to_evaluate)} files to evaluate.")
    
    for i, fpath in enumerate(files_to_evaluate):
        print(f"\n[{i+1}/{len(files_to_evaluate)}] Processing: {fpath}")
        evaluator.evaluate_file(fpath, max_workers=args.max_workers)
    
    print("\nEvaluation complete.")

if __name__ == "__main__":
    main()
