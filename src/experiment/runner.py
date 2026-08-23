import json
import os
import re
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.utils.llm_client import LLMClient
from src.core.witness import VisualWitness
from src.core.arbiter import Arbiter
from src.experiment.adaptive_router import AdaptiveRouter
from src.experiment.config import (
    TestCase,
    VISUAL_ATTACKS,
    get_conditions_for_phase,
    load_test_cases,
    resolve_context,
)
from src.attacks.visual_attacks import VisualAttacker


def parse_arbiter_response(content: str) -> Tuple[str, str]:
    """
    Robustly parse Arbiter response to extract reasoning and final answer.
    Handles various output formats including non-compliant ones from Qwen.
    
    Returns:
        Tuple[str, str]: (reasoning, final_answer)
    """
    if not content or not content.strip():
        return "", "[No response from model]"
    
    content = content.strip()
    reasoning = ""
    final_answer = ""
    
    # Strategy 1: Standard XML parsing with regex (handles malformed tags better)
    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL | re.IGNORECASE)
    if think_match:
        reasoning = think_match.group(1).strip()
    
    answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL | re.IGNORECASE)
    if answer_match:
        final_answer = answer_match.group(1).strip()
    
    # Strategy 2: Handle unclosed <answer> tag
    if not final_answer and '<answer>' in content.lower():
        # Find content after <answer> tag
        idx = content.lower().find('<answer>')
        if idx != -1:
            final_answer = content[idx + 8:].strip()
            # Clean up any trailing tags
            final_answer = re.sub(r'</?(think|answer)>.*', '', final_answer, flags=re.IGNORECASE | re.DOTALL).strip()
    
    # Strategy 3: If we have reasoning but no answer, look for content after </think>
    if reasoning and not final_answer:
        think_end = content.lower().find('</think>')
        if think_end != -1:
            remaining = content[think_end + 8:].strip()
            # Remove any stray XML tags
            remaining = re.sub(r'</?[a-zA-Z]+>', '', remaining).strip()
            if remaining:
                final_answer = remaining
    
    # Strategy 4: Look for "Final Answer:" or similar patterns
    if not final_answer:
        patterns = [
            r'(?:final\s*answer|answer|conclusion|result)\s*[:：]\s*(.+?)(?:\n\n|$)',
            r'(?:^|\n)(?:therefore|thus|so|hence)[,:]?\s*(.+?)(?:\n|$)',
            r'\*\*(.+?)\*\*',  # Bold text often used for emphasis
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                candidate = match.group(1).strip()
                # Only use if it's a reasonable length (not the whole content)
                if len(candidate) < len(content) * 0.5 and len(candidate) > 2:
                    final_answer = candidate
                    break
    
    # Strategy 5: If still no answer, use the whole content (minus think block)
    if not final_answer:
        # Remove think block if present
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
        # Remove any remaining XML-like tags
        cleaned = re.sub(r'</?[a-zA-Z]+>', '', cleaned).strip()
        if cleaned:
            final_answer = cleaned
        else:
            # Last resort: use original content
            final_answer = content
    
    # Final cleanup
    final_answer = final_answer.strip()
    
    # If answer is still too long (might be full reasoning), try to extract last sentence/paragraph
    if len(final_answer) > 500:
        # Look for a clear concluding statement
        lines = final_answer.split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line and len(line) > 10 and not line.startswith(('Step', '1.', '2.', '3.', '-', '*')):
                final_answer = line
                break
    
    return reasoning, final_answer

class ExperimentRunner:
    def __init__(self, data_dir: str, output_dir: str = "results"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.cases = self._load_cases()
        self.attacker = VisualAttacker()
        self._adaptive_router_cache: Dict[str, Optional[AdaptiveRouter]] = {}
        self.adaptive_router = AdaptiveRouter.load()
        if self.adaptive_router is not None:
            print(
                f"Loaded adaptive router from results/router_artifacts/adaptive_router_minimal.json "
                f"(tau={self.adaptive_router.threshold:.2f})"
            )
        else:
            print("Adaptive router artifact not found; adaptive_s2va will fall back to blind S2VA behavior.")
        
        # Load Toxic Text Map (Dose-Response)
        self.toxic_map = {}
        toxic_path = "data/toxic_abnormal.jsonl"
        if os.path.exists(toxic_path):
            print(f"Loading toxic texts from {toxic_path}...")
            with open(toxic_path) as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        self.toxic_map[str(d["case_id"])] = d
                    except: pass

    def _load_cases(self) -> List[TestCase]:
        """Load all test cases from the processed data directory."""
        return load_test_cases(self.data_dir)

    def run_experiment(
        self,
        models: List[str],
        phases: List[str],
        max_workers: int = 10,
        num_samples: int = None,
        selected_attacks: List[str] = None,
        include_extended_conditions: bool = False,
        selected_conditions: List[str] = None,
        image_type: str = None,
        case_ids: List[str] = None,
    ):
        """
        Run the full experiment matrix.
        phases: ['baseline_rag', 's2va']
        """
        # 1. Determine attacks to run
        attacks = selected_attacks if selected_attacks else VISUAL_ATTACKS
        
        # 2. Sample cases if requested
        run_cases = self.cases
        if image_type and image_type != "all":
            run_cases = [c for c in run_cases if c.image_type == image_type]
            print(f"Filtering to image_type={image_type}: {len(run_cases)} cases.")
        if case_ids:
            wanted = {str(cid) for cid in case_ids}
            run_cases = [c for c in run_cases if str(c.id) in wanted]
            print(f"Filtering to {len(wanted)} requested case IDs: {len(run_cases)} cases found.")
        if num_samples and num_samples < len(run_cases):
            import random
            random.seed(42)  # For reproducibility
            run_cases = random.sample(run_cases, num_samples)
            print(f"Sampling {num_samples} cases for this run.")

        for model_name in models:
            print(f"\n>>> Running experiments for model: {model_name}")
            client = LLMClient(model=model_name)
            
            for phase in phases:
                for attack in attacks:
                    conditions_to_run = selected_conditions or get_conditions_for_phase(phase, include_extended=include_extended_conditions)

                    for condition in conditions_to_run:
                        self._run_phase_condition(client, model_name, phase, attack, condition, max_workers, run_cases)

    def _run_phase_condition(self, client: LLMClient, model_name: str, phase: str, attack: str, condition: str, max_workers: int, run_cases: List[TestCase]):
        """Run a specific phase, attack, and condition combination."""
        
        # Check for completed tasks
        completed_keys = self._get_completed_keys(model_name, phase, attack, condition)
        tasks_to_run = [c for c in run_cases if str(c.id) not in completed_keys]
        
        if not tasks_to_run:
            return

        print(f"  Executing {phase} | {attack} | {condition} ({len(tasks_to_run)} tasks)...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for case in tasks_to_run:
                futures.append(executor.submit(self._run_single_task, client, case, phase, attack, condition))
            
            for i, future in enumerate(as_completed(futures)):
                try:
                    res = future.result()
                    if res:
                        self._save_result(model_name, phase, attack, condition, res)
                    
                    if (i + 1) % 10 == 0:
                        print(f"    Progress: {i + 1}/{len(tasks_to_run)}...")
                except Exception as e:
                    print(f"    Error in task: {e}")

        self._sort_results_file(model_name, phase, attack, condition)

    def _run_single_task(self, client: LLMClient, case: TestCase, phase: str, attack: str, condition: str) -> Dict[str, Any]:
        """Execute a single inference task."""
        try:
            # 1. Prepare Image with Attack
            img = self.attacker.load_image(case.image_path)
            if attack != "none":
                img = self.attacker.apply_attack(img, attack)
            
            # 2. Prepare Context
            if phase == "param_only":
                context = None
            else:
                context = resolve_context(case, condition, self.toxic_map)
            
            # 3. Run Inference
            if phase == "baseline_rag":
                return self._run_baseline_rag(client, case, img, context, condition, attack)
            elif phase == "baseline_rag_strong_visual":
                return self._run_baseline_rag_strong_visual(client, case, img, context, condition, attack)
            elif phase == "baseline_rag_ignore_context":
                return self._run_baseline_rag_ignore_context(client, case, img, context, condition, attack)
            elif phase == "s2va":
                return self._run_s2va(client, case, img, context, condition, attack)
            elif phase == "param_only":
                return self._run_param_only(client, case, img, condition, attack)
            elif phase == "cot_rag":
                return self._run_cot_rag(client, case, img, context, condition, attack)
            elif phase == "evidence_separation":
                return self._run_evidence_separation(client, case, img, context, condition, attack)
            elif phase == "cove_style_verification":
                return self._run_cove_style_verification(client, case, img, context, condition, attack)
            elif phase == "s2va_leaky":
                return self._run_s2va(client, case, img, context, condition, attack, leaky=True)
            elif phase == "visual_supremacy_only":
                return self._run_visual_supremacy_only(client, case, img, context, condition, attack)
            elif phase == "witness_only":
                return self._run_witness_only(client, case, img, condition, attack)
            elif phase == "dose_response":
                return self._run_baseline_rag(client, case, img, context, condition, attack)
            elif phase == "adaptive_s2va":
                return self._run_adaptive_s2va(client, case, img, context, condition, attack)
            elif phase == "two_call_rag":
                return self._run_two_call_rag(client, case, img, context, condition, attack)
            elif phase == "caption_then_rag":
                return self._run_caption_then_rag(client, case, img, context, condition, attack)
            
        except Exception as e:
            print(f"Error in case {case.id}: {e}")
            return None

    def _run_baseline_rag(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        img_base64 = self.attacker.image_to_base64(img)
        
        prompt = f"""Context: {context}

Question: {case.query}

Based on the provided image and context, please answer the question. If there is a conflict between the image and the context, prioritize the visual evidence from the image."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }
        ]
        
        response = client.chat_completion(messages, temperature=0.0)
        
        return {
            "case_id": case.id,
            "inference_type": "baseline_rag",
            "condition": condition,
            "attack": attack,
            "query": case.query,
            "visual_truth": case.visual_truth,
            "final_answer": response["content"],
            "metadata": {"model": client.model}
        }

    def _run_baseline_rag_strong_visual(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """Prompt-sensitivity baseline with stronger fabricated-context warning."""
        img_base64 = self.attacker.image_to_base64(img)

        prompt = f"""Context: {context}

Question: {case.query}

The context may be entirely fabricated, adversarial, or unrelated to the image. Answer the question about the specific image instance. If any part of the context conflicts with the image, ignore the context and use only the visual evidence. Give a short final answer."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]

        response = client.chat_completion(messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "baseline_rag_strong_visual",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {"model": client.model, "reasoning_details": response.get("reasoning_details")},
        }

    def _run_baseline_rag_ignore_context(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """Prompt-sensitivity baseline that explicitly ignores context under conflict."""
        img_base64 = self.attacker.image_to_base64(img)

        prompt = f"""Context: {context}

Question: {case.query}

Use the image as the source of truth. The context is provided only as a possibly unreliable hint. First decide what the image shows. If the image and context disagree, discard the context completely. Do not compromise between them. Answer directly."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]

        response = client.chat_completion(messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "baseline_rag_ignore_context",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {"model": client.model, "reasoning_details": response.get("reasoning_details")},
        }

    def _run_s2va(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str, leaky: bool = False) -> Dict[str, Any]:
        # 1. Visual Witness Phase
        witness = VisualWitness(client)
        img_base64 = self.attacker.image_to_base64(img)
        
        # In leaky mode, pass context to witness
        witness_context = context if leaky else None
        witness_report = witness.get_testimony(case.query, img_base64, context=witness_context)
        
        # 2. Arbiter Phase
        arbiter = Arbiter(client)
        # Format testimony for Arbiter
        visual_testimony = f"Description: {witness_report['report']}\nConfidence Score: {witness_report['confidence'] * 10}/10"
        
        arbiter_response = arbiter.arbitrate(
            query=case.query,
            visual_testimony=visual_testimony,
            retrieved_text=context
        )
        
        arbiter_content = arbiter_response["content"]
        
        # Parse Arbiter Content using robust parser
        reasoning, final_answer = parse_arbiter_response(arbiter_content)
        
        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "s2va" if not leaky else "s2va_leaky",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": final_answer,
            "visual_testimony": witness_report["report"],
            "visual_confidence": witness_report["confidence"],
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "witness_reasoning": None,
                "arbiter_reasoning": reasoning,
                "raw_arbiter_content": arbiter_content,  # Store raw for debugging
                "reasoning_details": arbiter_response.get("reasoning_details")
            }
        }

    def _run_adaptive_s2va(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """Adaptive routing: use blind witness to decide whether to invoke S2VA."""
        witness = VisualWitness(client)
        img_base64 = self.attacker.image_to_base64(img)

        witness_report = witness.get_testimony(case.query, img_base64, context=None)

        router = self._get_adaptive_router(client.model)
        if router is None:
            # Fallback to standard S2VA if no router artifact is available.
            return self._run_s2va(client, case, img, context, condition, attack)

        use_s2va, router_prob = router.should_use_s2va(case, witness_report)
        router_meta = {
            "router_prob": router_prob,
            "router_threshold": router.threshold,
            "router_decision": "s2va" if use_s2va else "baseline",
            "router_cv_accuracy": router.cv_accuracy,
            "router_threshold_accuracy": router.threshold_accuracy,
            "router_baseline_accuracy": router.baseline_accuracy,
            "router_s2va_accuracy": router.s2va_accuracy,
            "router_oracle_accuracy": router.oracle_accuracy,
        }

        if not use_s2va:
            baseline = self._run_baseline_rag(client, case, img, context, condition, attack)
            baseline["inference_type"] = "adaptive_s2va"
            baseline["visual_testimony"] = witness_report["report"]
            baseline["visual_confidence"] = witness_report["confidence"]
            baseline["metadata"].update(
                {
                    **router_meta,
                    "model": client.model,
                    "router_mode": "fallback_baseline",
                    "witness_reasoning": None,
                }
            )
            return baseline

        arbiter = Arbiter(client)
        visual_testimony = f"Description: {witness_report['report']}\nConfidence Score: {witness_report['confidence'] * 10}/10"
        arbiter_response = arbiter.arbitrate(
            query=case.query,
            visual_testimony=visual_testimony,
            retrieved_text=context,
        )
        arbiter_content = arbiter_response["content"]
        reasoning, final_answer = parse_arbiter_response(arbiter_content)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "adaptive_s2va",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": final_answer,
            "visual_testimony": witness_report["report"],
            "visual_confidence": witness_report["confidence"],
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "witness_reasoning": None,
                "arbiter_reasoning": reasoning,
                "raw_arbiter_content": arbiter_content,
                "reasoning_details": arbiter_response.get("reasoning_details"),
                **router_meta,
                "router_mode": "adaptive_s2va",
            },
        }

    def _get_adaptive_router(self, model_name: str) -> Optional[AdaptiveRouter]:
        if model_name in self._adaptive_router_cache:
            return self._adaptive_router_cache[model_name]

        router = AdaptiveRouter.load(model_name=model_name)
        self._adaptive_router_cache[model_name] = router
        if router is not None:
            print(
                f"Loaded adaptive router for {model_name} "
                f"(tau={router.threshold:.2f}, cv={router.cv_accuracy:.2%})"
            )
        return router


    def _run_param_only(self, client: LLMClient, case: TestCase, img: Any, condition: str, attack: str) -> Dict[str, Any]:
        img_base64 = self.attacker.image_to_base64(img)
        
        # Explicitly ask to base the answer on the image
        prompt = f"""Question: {case.query}

Based on the provided image, please answer the question."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }
        ]
        
        response = client.chat_completion(messages, temperature=0.0)
        
        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "param_only",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "reasoning_details": response.get("reasoning_details")
            }
        }

    def _run_cot_rag(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        img_base64 = self.attacker.image_to_base64(img)
        
        prompt = f"""Context: {context}

Question: {case.query}

Instruction:
1. The provided context might be incorrect or misleading.
2. First, verify the facts by looking closely at the image. 
3. Think step-by-step: compare the visual evidence with the context.
4. If there is a conflict, prioritize the visual evidence.
5. Finally, answer the question."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }
        ]
        
        response = client.chat_completion(messages, temperature=0.0)
        
        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "cot_rag",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "reasoning_details": response.get("reasoning_details")
            }
        }

    def _run_evidence_separation(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """
        Strong single-call black-box verification baseline.
        The model must separate visual evidence from textual evidence before resolving.
        """
        img_base64 = self.attacker.image_to_base64(img)

        prompt = f"""Context: {context}

Question: {case.query}

Resolve this as a conflict-aware multimodal judge.
1. List only the visual evidence relevant to the question.
2. List only the textual-context evidence relevant to the question.
3. State whether the two sources conflict.
4. If they conflict, answer using the visual evidence from the image, not the context.
5. Finish with: Final Answer: <short answer>."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]

        response = client.chat_completion(messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "evidence_separation",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {"model": client.model, "reasoning_details": response.get("reasoning_details")},
        }

    def _run_cove_style_verification(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """
        Black-box CoVe-style baseline.
        Call 1 produces a normal RAG answer. Call 2 revises it after an image-focused
        verification pass, but the retrieved context remains visible in the verifier.
        """
        img_base64 = self.attacker.image_to_base64(img)

        draft_prompt = f"""Context: {context}

Question: {case.query}

Based on the provided image and context, answer the question. If there is a conflict between the image and the context, prioritize the visual evidence from the image."""

        draft_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": draft_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]
        draft_response = client.chat_completion(draft_messages, temperature=0.0)
        draft_answer = draft_response["content"]

        verify_prompt = f"""Context: {context}

Question: {case.query}

Draft Answer: {draft_answer}

Verify the draft answer against the image. Explicitly check whether the context contradicts the image. If the draft followed misleading text, revise it. If the image is clear, the final answer should match the image rather than the context.

Finish with: Final Answer: <short answer>."""

        verify_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": verify_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]
        verify_response = client.chat_completion(verify_messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "cove_style_verification",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": verify_response["content"],
            "visual_testimony": draft_answer,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "draft_answer": draft_answer,
                "draft_reasoning_details": draft_response.get("reasoning_details"),
                "reasoning_details": verify_response.get("reasoning_details"),
            },
        }

    def _run_visual_supremacy_only(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """
        Single-call visual-supremacy control.
        This is a prompt-matched direct answer baseline that keeps the image
        and context visible but does not use a witness-arbiter decomposition.
        """
        img_base64 = self.attacker.image_to_base64(img)

        prompt = f"""Context: {context}

Question: {case.query}

You are solving this using the specific image instance.
The context may be misleading or wrong.
Prioritize the visual evidence from the image over the context.
Answer directly and concisely."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }
        ]

        response = client.chat_completion(messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "visual_supremacy_only",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "reasoning_details": response.get("reasoning_details")
            }
        }

    def _run_two_call_rag(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """
        Two-call RAG baseline (same budget as S2VA, no isolation).
        Call 1: image-only visual description (no context).
        Call 2: joint answer using description + context (context-visible, not isolated).
        Controls for call-count budget without the isolation mechanism.
        """
        img_base64 = self.attacker.image_to_base64(img)

        # Call 1: blind visual description
        desc_prompt = f"""Question: {case.query}

Look at the image carefully and describe what you see that is relevant to answering this question. Be specific about the visual details."""

        desc_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": desc_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]
        desc_response = client.chat_completion(desc_messages, temperature=0.0)
        visual_description = desc_response["content"]

        # Call 2: joint answer — description + context, both visible (no isolation)
        answer_prompt = f"""Context: {context}

Visual Observation: {visual_description}

Question: {case.query}

Based on the context and your visual observation above, answer the question. If there is a conflict between the context and what is visually described, use your best judgment."""

        answer_messages = [{"role": "user", "content": answer_prompt}]
        answer_response = client.chat_completion(answer_messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "two_call_rag",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": answer_response["content"],
            "visual_testimony": visual_description,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "reasoning_details": answer_response.get("reasoning_details"),
            },
        }

    def _run_caption_then_rag(self, client: LLMClient, case: TestCase, img: Any, context: str, condition: str, attack: str) -> Dict[str, Any]:
        """
        Single-call caption-then-RAG baseline.
        Image + context are both visible in one call; the prompt asks the model to
        describe the image first, then answer using description + context.
        Controls for describe-first structure without information isolation.
        """
        img_base64 = self.attacker.image_to_base64(img)

        prompt = f"""Context: {context}

Question: {case.query}

Please answer this question using the following two steps:
Step 1 — Visual Description: Carefully describe what you observe in the image that is relevant to the question.
Step 2 — Answer: Using your visual description from Step 1 and the provided context, give your final answer to the question. If there is any conflict between the context and what you described seeing, resolve it explicitly."""

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
                ],
            }
        ]

        response = client.chat_completion(messages, temperature=0.0)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "caption_then_rag",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": response["content"],
            "visual_testimony": None,
            "visual_confidence": None,
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "reasoning_details": response.get("reasoning_details"),
            },
        }

    def _run_witness_only(self, client: LLMClient, case: TestCase, img: Any, condition: str, attack: str) -> Dict[str, Any]:
        """
        Blind visual witness control.
        The model answers directly from the image without any retrieved context.
        """
        witness = VisualWitness(client)
        img_base64 = self.attacker.image_to_base64(img)
        witness_answer = witness.get_direct_answer(case.query, img_base64)

        return {
            "case_id": case.id,
            "model_name": client.model,
            "inference_type": "witness_only",
            "query": case.query,
            "condition": condition,
            "attack": attack,
            "visual_truth": case.visual_truth,
            "blur_level": 0.0,
            "final_answer": witness_answer["answer"],
            "visual_testimony": witness_answer["answer"],
            "visual_confidence": witness_answer["confidence"],
            "correctness_score": None,
            "common_sense_score": None,
            "text_faithfulness_score": None,
            "visual_faithfulness_score": None,
            "metadata": {
                "model": client.model,
                "mode": "witness_only",
            }
        }

    def _get_result_path(self, model_name: str, phase: str, attack: str, condition: str) -> str:
        model_slug = model_name.replace("/", "_")
        if phase == "param_only":
            return os.path.join(self.output_dir, model_slug, "param_only.jsonl")
        if phase in {
            "baseline_rag",
            "baseline_rag_strong_visual",
            "baseline_rag_ignore_context",
            "cot_rag",
            "evidence_separation",
            "cove_style_verification",
            "two_call_rag",
            "caption_then_rag",
        } and attack == "none":
            return os.path.join(self.output_dir, model_slug, phase, f"{condition}.jsonl")
        return os.path.join(self.output_dir, model_slug, phase, attack, f"{condition}.jsonl")

    def _save_result(self, model_name: str, phase: str, attack: str, condition: str, result: Dict[str, Any]):
        fpath = self._get_result_path(model_name, phase, attack, condition)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "a") as f:
            f.write(json.dumps(result) + "\n")

    def _get_completed_keys(self, model_name: str, phase: str, attack: str, condition: str) -> set:
        fpath = self._get_result_path(model_name, phase, attack, condition)
        completed = set()
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        completed.add(str(data.get("case_id")))
                    except:
                        pass
        return completed

    def _sort_results_file(self, model_name: str, phase: str, attack: str, condition: str):
        fpath = self._get_result_path(model_name, phase, attack, condition)
        if not os.path.exists(fpath):
            return
            
        results = []
        with open(fpath, "r") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        results.sort(key=lambda x: int(x.get("case_id", 0)) if str(x.get("case_id")).isdigit() else str(x.get("case_id")))
        
        with open(fpath, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
