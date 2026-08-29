import argparse

from _bootstrap import REPO_ROOT  # noqa: F401
from src.experiment.config import SUPPORTED_PHASES
from src.experiment.runner import ExperimentRunner

def main():
    parser = argparse.ArgumentParser(description="Run S2VA Inference (No Evaluation)")
    parser.add_argument("--data_dir", type=str, default="data/processed", help="Directory containing test case JSONs")
    parser.add_argument("--output_dir", type=str, default="results", help="Directory to save results")
    parser.add_argument("--models", type=str, nargs="+", default=["openai/gpt-4o"], help="List of models to evaluate")
    parser.add_argument("--phases", type=str, nargs="+", default=["baseline_rag", "s2va"], choices=list(SUPPORTED_PHASES), help="Phases to execute")
    parser.add_argument("--num_samples", type=int, default=None, help="Number of random samples to run (for cost saving)")
    parser.add_argument("--attacks", type=str, nargs="+", default=["none"], help="Specific attacks to run (e.g., none snow_severe)")
    parser.add_argument("--conditions", type=str, nargs="+", default=None, help="Specific text conditions to run (e.g., false_text true_text)")
    parser.add_argument("--image_type", type=str, default=None, choices=["abnormal", "normal", "all"], help="Optional image type filter")
    parser.add_argument("--case_ids", type=str, nargs="+", default=None, help="Optional explicit case IDs to run")
    parser.add_argument("--max_workers", type=int, default=30, help="Number of parallel threads")
    parser.add_argument("--extended_conditions", action="store_true", help="Enable extended context conditions")
    args = parser.parse_args()

    runner = ExperimentRunner(data_dir=args.data_dir, output_dir=args.output_dir)
    
    print(f"Starting inference on data from: {args.data_dir}")
    print(f"Models to evaluate: {args.models}")
    print(f"Phases to run: {args.phases}")
    print(f"Max workers: {args.max_workers}")
    
    runner.run_experiment(
        models=args.models,
        phases=args.phases,
        max_workers=args.max_workers,
        num_samples=args.num_samples,
        selected_attacks=args.attacks,
        include_extended_conditions=args.extended_conditions,
        selected_conditions=args.conditions,
        image_type=args.image_type,
        case_ids=args.case_ids,
    )
    print("Inference complete.")

if __name__ == "__main__":
    main()
