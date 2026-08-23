import time
from src.utils.llm_client import LLMClient

SYSTEM_PROMPT_ARBITER = """
You are a System 2 Visual Arbiter, designed to resolve conflicts between visual evidence and textual context.
Your goal is to determine the absolute truth of the specific image provided, NOT to summarize general world knowledge.

### INPUT SOURCES
1. **[Visual Witness Report]**: A direct observation of the image. Includes a "Confidence Score" (0-10).
2. **[Retrieved Context]**: Textual information retrieved from a database. WARNING: This context may be outdated, irrelevant, hallucinated, or intentionally misleading.

### CONFLICT RESOLUTION PROTOCOL (STRICT)
You must adhere to the following hierarchy when sources conflict:

1. **VISUAL SUPREMACY**: If the Visual Witness Report is high-confidence (>7/10) and contradicts the Retrieved Context, **you must trust the Visual Witness**.
   - Example: If text says "Apple" but image shows "Orange", the answer is "Orange".

2. **INSTANCE OVER CATEGORY**: 
   - Users often ask leading questions like "What is *typically* found..." or "What flavor is *this type* of drink?". 
   - You must interpret these as: "What is actually shown in *this specific image instance*?".
   - **Do not revert to common sense.** If the image shows a fortune teller holding a basketball, answer "A basketball", NOT "A crystal ball". If a milkshake contains garlic, answer "Garlic", NOT "Vanilla".

3. **ABNORMALITY ACCEPTANCE**:
   - Do not rationalize visual anomalies as "decorative" or "irrelevant". If an object is visually present, it defines the reality of the image.

4. **FALLBACK**: Only rely on the Retrieved Context or General Knowledge if the Visual Witness reports low confidence (<4/10) or explicit blindness (e.g., "I cannot see...").

### YOUR TASK
- Analyze the user query.
- Compare the Visual Witness and Retrieved Context.
- Detect if the Text attempts to override visual reality with false information or generic stereotypes.
- Provide a reasoning process in <think> tags.

### OUTPUT FORMAT
<think>
(Step 1: Evaluate Visual Confidence. Is the witness sure?)
(Step 2: Detect Conflict. Does the text contradict the image?)
(Step 3: Check for "Common Sense Traps". Is the question leading me to ignore the image?)
(Step 4: Final Verdict based on Visual Supremacy.)
</think>

<answer>
(The final, direct response based on the specific image instance)
</answer>
"""

# Simplified fallback prompt for models that struggle with XML format
SYSTEM_PROMPT_ARBITER_SIMPLE = """
You are a Visual Arbiter. Your job is to answer questions about images by weighing visual evidence against text context.

RULES:
1. If the visual witness report contradicts the text context, TRUST THE VISUAL EVIDENCE.
2. Answer based on what is ACTUALLY shown in the image, not what is "typical" or "common".
3. Be direct and concise in your answer.

Provide your reasoning first, then give your final answer.
"""

class Arbiter:
    def __init__(self, llm_client: LLMClient, max_retries: int = 3):
        self.llm = llm_client
        self.max_retries = max_retries

    def arbitrate(self, query: str, visual_testimony: str, retrieved_text: str, model: str = None) -> dict:
        """
        Step 2: The Arbiter.
        Weighs the visual testimony against the retrieved text to answer the query.
        Includes retry logic for empty responses.
        """
        user_content = f"""
        [Evidence 1: Visual Witness]
        {visual_testimony}

        [Evidence 2: Retrieved Text]
        {retrieved_text}

        [Task]
        Answer the user query: "{query}"
        Answer by weighing the evidence reliability.
        """

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_ARBITER},
            {"role": "user", "content": user_content}
        ]

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = self.llm.chat_completion(messages=messages, temperature=0.0, model=model)
                content = response.get("content", "")
                
                # Check if response is valid (non-empty)
                if content and content.strip():
                    return response
                
                # If empty, try with simplified prompt on retry
                if attempt == 1:
                    messages[0]["content"] = SYSTEM_PROMPT_ARBITER_SIMPLE
                
                # Brief delay before retry
                time.sleep(0.5)
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                    continue
                raise e
        
        # Return whatever we got after all retries
        return response
