import json
from typing import Dict, Any
from src.utils.llm_client import LLMClient

class VisualWitness:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def get_testimony(self, query: str, image_b64: str, context: str = None) -> Dict[str, Any]:
        """
        Step 1: Visual Witness.
        Gets a description and confidence score from the image.
        If context is provided (Leaky Mode), it simulates a pipeline where visual perception is contaminated by text.
        """
        if context:
            # Leaky Prompt: Encourage using context
            system_prompt = f"""You are a Visual Witness. Your task is to describe the image content.
I will provide you with retrieved context that may contain important information about the image.
You should use this context to help you identify objects and understand the scene, as the image might be ambiguous.

Context:
<context>
{context}
</context>

Focus on the specific question asked, but prioritizing describing what you see.
If the image is blurry, dark, or obscured (e.g., by rain or snow), you MUST report this and lower your confidence.

Output strictly in JSON format:
{{
    "report": "Detailed description, incorporating context if helpful",
    "confidence": 0.0 to 1.0 (float)
}}"""
        else:
            # Blind Prompt: Objective isolation (Standard S2VA)
            system_prompt = """You are a Blind Visual Witness. Your task is to describe the image content OBJECTIVELY without knowing the context.
Focus on the specific question asked, but only report what you see.
If the image is blurry, dark, or obscured (e.g., by rain or snow), you MUST report this and lower your confidence.

Output strictly in JSON format:
{
    "report": "Detailed objective description",
    "confidence": 0.0 to 1.0 (float)
}"""
        
        user_prompt = f"Question to keep in mind: {query}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ]
        
        try:
            response = self.llm.chat_completion(messages=messages, temperature=0.0)
            content = response["content"]
            
            # Simple JSON parsing
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]
                
            return json.loads(content)
        except Exception as e:
            return {
                "report": f"Error in witness: {str(e)}",
                "confidence": 0.0
            }

    def get_direct_answer(self, query: str, image_b64: str) -> Dict[str, Any]:
        """
        Blind visual answer used for the witness-only control.
        This asks the model to answer the question directly from the image
        without any retrieved context.
        """
        system_prompt = """You are a Blind Visual Witness. Answer the user's question using only the image.
Do not use retrieved text or outside knowledge.
If the image is blurry, dark, or obscured, say so and lower your confidence.

Output strictly in JSON format:
{
    "answer": "Short direct answer",
    "confidence": 0.0 to 1.0 (float)
}"""

        user_prompt = f"Question to answer from the image only: {query}"

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ],
            },
        ]

        try:
            response = self.llm.chat_completion(messages=messages, temperature=0.0)
            content = response["content"]

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                content = content[start:end]

            parsed = json.loads(content)
            return {
                "answer": parsed.get("answer", ""),
                "confidence": float(parsed.get("confidence", 0.0) or 0.0),
            }
        except Exception as e:
            return {
                "answer": f"Error in witness-only answer: {str(e)}",
                "confidence": 0.0,
            }
