import os
import requests
from typing import List, Dict, Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None


def _load_env_file(path: str = ".env") -> None:
    """Load a simple .env file without requiring python-dotenv."""
    if not os.path.exists(path):
        return

    try:
        with open(path, "r") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return


if load_dotenv is not None:
    load_dotenv()
else:
    _load_env_file()

class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://openrouter.ai/api/v1", model: str = "google/gemini-3-pro-image-preview"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url
        self.model = model
        
        if not self.api_key:
            raise ValueError("API key must be provided either via parameter or OPENROUTER_API_KEY environment variable")

    def chat_completion(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None, max_tokens: int = 2000, model: Optional[str] = None, include_reasoning: bool = False) -> Dict[str, Any]:
        """
        Wrapper for chat completion using requests (compatible with OpenRouter).
        Returns a dictionary with 'content' and optional 'reasoning_details'.
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/anonymous/multimodal-conflict",
            "X-Title": "S2VA Experiment"
        }
        
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens
        }
        
        if include_reasoning:
            payload["reasoning"] = {"enabled": True}
        
        if temperature is not None:
            payload["temperature"] = temperature
        
        import time
        
        max_retries = 1  # Fail fast
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Reduced timeout to 60s for faster skipping of stuck tasks
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                
                if 'choices' not in result:
                    raise KeyError(f"Response missing 'choices' key. Full response: {result}")
                
                message = result['choices'][0]['message']
                
                return {
                    "content": message.get('content', ''),
                    "reasoning_details": message.get('reasoning_details', None)
                }
                
            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                print(f"⚠️ API Error (Attempt {attempt+1}/{max_retries}): {e}")
                if hasattr(e, 'response') and e.response is not None:
                     print(f"   Response content: {e.response.text[:200]}...")
                
                if attempt < max_retries - 1:
                    sleep_time = base_delay * (2 ** attempt)  # 2, 4, 8, 16, 32s
                    print(f"   Waiting {sleep_time}s before retrying...")
                    time.sleep(sleep_time)
                else:
                    print("❌ Max retries reached.")
                    raise e
