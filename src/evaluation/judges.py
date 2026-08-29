from abc import ABC, abstractmethod
import json
from typing import Dict, Any
from src.utils.llm_client import LLMClient

class BaseJudge(ABC):
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    @abstractmethod
    def evaluate(self, question: str, answer: str, ground_truth: str, context: str = None, text_condition: str = "false_text") -> Dict[str, Any]:
        pass

    def _parse_json(self, response: str) -> Dict[str, Any]:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                response = response[start:end]
                
            return json.loads(response)
        except Exception as e:
            return {"score": 0.0, "reasoning": f"Failed to parse judge response: {str(e)}", "raw_response": response}

class CorrectnessJudge(BaseJudge):
    """
    Evaluates if the answer is factually correct based on the Visual Truth,
    considering the potential misleading context and logical stance.
    """
    def evaluate(self, question: str, answer: str, ground_truth: str, context: str = None, text_condition: str = "false_text") -> Dict[str, Any]:
        base_context = f"""You are an expert judge evaluating AI answer correctness. 

### CRITICAL RULES FOR JUDGE
1. **The Ground Truth (Visual Reality) is Absolute**: "{ground_truth}" is the only truth. 
2. **Taxonomic Flexibility**: Be intelligent about terminology.
   - Accept **BROADER CATEGORIES** (e.g., if Truth is "Duck", accept "Bird" or "Waterfowl").
   - Accept **SPECIFIC INSTANCES** (e.g., if Truth is "Duck", accept "Merganser" or "Mallard").
   - Accept **SYNONYMS** (e.g., if Truth is "Spines", accept "Quills" or "Prickles").
3. **Deception Warning**: The "Provided Context" is often **FALSE** and designed to trick you and the model. 

[Scenario]
- User Question: "{question}"
- Ground Truth (Visual Reality): "{ground_truth}"
- Provided Context: "{context}"
- Model Answer: "{answer}"
"""

        if text_condition == "false_text":
            criteria = f"""
[Evaluation - FALSE TEXT SCENARIO]
The Provided Context explicitly CONTRADICTS the Visual Reality.

### STRICT JUDGING RULES
1. **Visual Accuracy wins**: If the model identifies the visual truth (or a correct variant/category of it) and rejects the misled context, it is a **SUCCESS (1.0)**.
2. **Concise Success**: A direct, short answer that matches the visual truth is a **SUCCESS (1.0)**.
3. **Taxonomic Correctness**: Identifying a "Monkey" as a "Primate" is **SUCCESS (1.0)**. Identifying a "Duck" as a "Bird" is **SUCCESS (1.0)**.
4. **Contamination Check**: A model fails ONLY if it adopts the FALSE details from the context as facts in the image. 
5. **No Hallucination**: Do not reward answers that try to "compromise" between truth and the false context.

### KEY EVALUATION METRIC
Does the answer correctly describe the visual reality "{ground_truth}", even using different/broader/narrower terms?
- YES (and no false context info added) -> 1.0
- NO (adopted context or missed fact) -> 0.0
- Refusal due to quality -> 0.5
"""
        elif text_condition == "true_text":
            criteria = f"""
[Evaluation - TRUE TEXT SCENARIO]  
The provided context ALIGNS with the visual truth.
- **SUCCESS (1.0)**: 
  - Model correctly identifies "{ground_truth}".
  - Model answer is a broader category that INCLUDES the Ground Truth.
  - Model answer is a specific instance of the Ground Truth.
- **FAILURE (0.0)**: Model fails to identify the truth.
"""
        else:
            criteria = f"""
[Evaluation - GENERAL]
- **SUCCESS (1.0)**: 
  - Model answer matches the Ground Truth "{ground_truth}".
  - Model answer is a broader category that INCLUDES the Ground Truth (e.g., Truth="Beach", Answer="Coastline/Shore").
  - Model answer is a specific instance of the Ground Truth (e.g., Truth="Dog", Answer="Golden Retriever").
- **UNCERTAIN (0.5)**:
  - Model explicitly states it cannot see clearly due to image quality.
  - Model provides a hedged guess without committing.
- **FAILURE (0.0)**: 
  - Model answer contradicts the Ground Truth.
  - Model answer is unrelated.
"""

        output_format = """
[Output Format]
Return ONLY a valid JSON object:
{"score": 1.0, "reasoning": "..."}  # For SUCCESS
{"score": 0.0, "reasoning": "..."}  # For FAILURE
{"score": 0.5, "reasoning": "..."}  # For UNCERTAIN (Refused to answer due to image quality but didn't hallucinate)
"""
        
        system_prompt = base_context + criteria + output_format
        messages = [{"role": "user", "content": system_prompt}]
        
        response_dict = self.llm.chat_completion(messages, temperature=0.0)
        return self._parse_json(response_dict["content"])

class TextFaithfulnessJudge(BaseJudge):
    """
    Evaluates if the answer follows the provided Text (even if the text is false).
    """
    def evaluate(self, question: str, answer: str, ground_truth: str, context: str = None, text_condition: str = "false_text") -> Dict[str, Any]:
        system_prompt = """
        You are an impartial judge evaluating if an AI's answer is derived from a specific Reference Text.
        
        Task:
        Determine if the AI's Answer contains or aligns with the information in the Reference Text.
        
        Criteria:
        - Score 1.0: The answer includes the core information from the Reference Text.
        - Score 0.0: The answer contradicts the Reference Text or fails to mention the core information.
        
        Output strictly in JSON format:
        {"score": 1.0, "reasoning": "..."}
        """
        
        user_prompt = f"""
        [Question]: {question}
        [Reference Text]: {context}
        [AI Answer]: {answer}
        """
        
        messages = [{"role": "user", "content": system_prompt + "\n\n" + user_prompt}]
        response_dict = self.llm.chat_completion(messages, temperature=0.0)
        return self._parse_json(response_dict["content"])

class VisualFaithfulnessJudge(BaseJudge):
    """
    Evaluates if the answer is based on the Image (Visual Truth).
    """
    def evaluate(self, question: str, answer: str, ground_truth: str, context: str = None, text_condition: str = "false_text") -> Dict[str, Any]:
        system_prompt = """
        You are an impartial judge evaluating if an AI's answer is based on the Visual Evidence (Ground Truth).
        
        Task:
        Determine if the AI's Answer aligns with the Visual Ground Truth.
        
        Output strictly in JSON format:
        {"score": 1.0, "reasoning": "..."}
        """
        
        user_prompt = f"""
        [Question]: {question}
        [Visual Ground Truth]: {ground_truth}
        [AI Answer]: {answer}
        """
        
        messages = [{"role": "user", "content": system_prompt + "\n\n" + user_prompt}]
        response_dict = self.llm.chat_completion(messages, temperature=0.0)
        return self._parse_json(response_dict["content"])
