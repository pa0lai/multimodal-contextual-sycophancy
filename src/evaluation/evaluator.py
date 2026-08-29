import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from src.utils.llm_client import LLMClient
from src.experiment.config import TestCase, load_test_cases_map, resolve_context
from src.evaluation.judges import CorrectnessJudge, TextFaithfulnessJudge, VisualFaithfulnessJudge

class Evaluator:
    def __init__(self, data_dir: str, output_dir: str = "results", judge_model: str = "openai/gpt-4o-mini"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        
        # Judges - Use dedicated client
        self.judge_client = LLMClient(model=judge_model)
        self.correctness_judge = CorrectnessJudge(self.judge_client)
        self.text_judge = TextFaithfulnessJudge(self.judge_client)
        self.visual_judge = VisualFaithfulnessJudge(self.judge_client)
        
        self.cases_map = self._load_cases_map(data_dir)
        self.file_lock = threading.Lock()

    def _load_cases_map(self, data_dir: str) -> Dict[str, TestCase]:
        """Load all test cases and map them by ID for quick lookup."""
        return load_test_cases_map(data_dir)

    def evaluate_file(self, input_file: str, max_workers: int = 10):
        """Evaluate a single JSONL result file with incremental saving (Safe Version)."""
        if not os.path.exists(input_file):
            print(f"File not found: {input_file}")
            return

        print(f"Evaluating {input_file}...")
        
        # 1. Read ALL results into a dictionary keyed by case_id to preserve everything
        all_data_map = {}
        case_ids_ordered = []
        tasks_to_eval = []
        
        with open(input_file, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    cid = str(data.get("case_id"))
                    all_data_map[cid] = data
                    case_ids_ordered.append(cid)
                    
                    # Check if it needs evaluation
                    if data.get("correctness_score") is None:
                        tasks_to_eval.append(data)
        
        if not tasks_to_eval:
            print(f"All cases in {input_file} are already evaluated. Skipping.")
            return

        print(f"Found {len(tasks_to_eval)} cases to evaluate (out of {len(all_data_map)} total).")
        
        # 2. Run evaluation in parallel
        evaluated_count = 0
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._evaluate_single_result, res): res for res in tasks_to_eval}
                
                for future in as_completed(futures):
                    try:
                        res = future.result()
                        if res:
                            # Update the map with evaluated result
                            cid = str(res.get("case_id"))
                            all_data_map[cid] = res
                            evaluated_count += 1
                            
                            # Real-time progress update
                            if evaluated_count % 10 == 0:
                                print(f"    Progress: {evaluated_count}/{len(tasks_to_eval)}...")
                                # Save everything (including non-evaluated ones) to prevent loss
                                self._save_full_results(input_file, all_data_map, case_ids_ordered)
                    except Exception as e:
                        print(f"Error evaluating result: {e}")
        except KeyboardInterrupt:
            print("\nEvaluation interrupted by user. Saving progress...")
        finally:
            # 3. Final Save (Always save the full map)
            self._save_full_results(input_file, all_data_map, case_ids_ordered)
            print(f"Finished session for {input_file}. Total evaluated this run: {evaluated_count}")

    def _save_full_results(self, input_file: str, data_map: Dict[str, Any], order: List[str]):
        """Save the full dataset back to file, preserving order."""
        temp_file = input_file + ".tmp"
        with self.file_lock:
            with open(temp_file, "w") as f:
                for cid in order:
                    f.write(json.dumps(data_map[cid]) + "\n")
            os.replace(temp_file, input_file)

    def _evaluate_single_result(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        case_id = str(result_data.get("case_id"))
        case = self.cases_map.get(case_id)
        
        if not case:
            print(f"Warning: Case ID {case_id} not found in data directory.")
            return result_data
        
        # Reconstruct ExperimentResult-like object or just update dict
        # We update the dict directly
        
        inference_type = result_data.get("inference_type") or "param_only"
        
        # Skip if already evaluated (for param_only)
        if inference_type == "param_only" and result_data.get("correctness_score") is not None:
            return result_data

        final_answer = result_data.get("final_answer", "")
        context_text = ""  # Need to determine context text if we want to eval text faithfulness
        
        # Determine context text based on condition
        condition = result_data.get("condition") or "none"
        if condition != "none":
            context_text = resolve_context(case, condition)

        metadata = result_data.get("metadata", {})
        
        # Prepare the answer for the judge
        # For S2VA, we want the judge to see the reasoning too for a fair comparison with baseline
        if "s2va" in inference_type:
            reasoning = metadata.get("arbiter_reasoning", "")
            if reasoning:
                judge_answer = f"Reasoning: {reasoning}\n\nFinal Answer: {final_answer}"
            else:
                judge_answer = final_answer
        else:
            judge_answer = final_answer

        judge_condition = condition
        if condition == "correct_context":
            judge_condition = "true_text"
        elif condition in {"weak_text", "medium_text", "strong_text", "shuffled_context"}:
            judge_condition = "false_text"
        elif condition == "no_context":
            judge_condition = "none"

        try:
            # Special logic for Param-Only: Calculate Common Sense Alignment
            if inference_type == "param_only":

                # For Abnormal cases, False Text represents Common Sense
                # For Normal cases, True Text represents Common Sense (since it aligns with visual truth)
                common_sense_ref = case.false_text if case.image_type == "abnormal" else case.true_text
                
                cs = self.text_judge.evaluate(case.query, final_answer, "", context=common_sense_ref, text_condition="true_text")
                result_data["common_sense_score"] = cs.get("score", 0.0)
                metadata["common_sense_reasoning"] = cs.get("reasoning", "")
                
                # Ensure context is empty for correctness judge
                context_text = ""
                judge_condition = "none"

            # For other phases (Baseline RAG, S2VA), run standard evaluations
            
            # 1. Correctness (vs Visual Truth, considering context)
            corr = self.correctness_judge.evaluate(
                question=case.query, 
                answer=judge_answer, 
                ground_truth=case.visual_truth,
                context=context_text,
                text_condition=judge_condition
            )
            result_data["correctness_score"] = corr.get("score", 0.0)
            metadata["correctness_reasoning"] = corr.get("reasoning", "")
            
            # 2. Text Faithfulness
            if context_text:
                tf = self.text_judge.evaluate(case.query, judge_answer, "", context=context_text, text_condition=judge_condition)
                result_data["text_faithfulness_score"] = tf.get("score", 0.0)
                metadata["text_faithfulness_reasoning"] = tf.get("reasoning", "")
            
            # 3. Visual Faithfulness
            vf = self.visual_judge.evaluate(case.query, judge_answer, case.visual_truth, text_condition=judge_condition)
            result_data["visual_faithfulness_score"] = vf.get("score", 0.0)
            metadata["visual_faithfulness_reasoning"] = vf.get("reasoning", "")

            
            result_data["metadata"] = metadata
            return result_data

        except Exception as e:
            import traceback
            print(f"Error evaluating case {case_id}: {e}")
            print(traceback.format_exc())
            return result_data
