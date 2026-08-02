import json
import os
from typing import Tuple

import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
MAX_HTML_CHARS = int(os.getenv("FINAL_VALIDATION_MAX_HTML_CHARS", "5000"))


def final_validation(html_chunk: str) -> Tuple[bool, str]:
    """
    Validate whether an HTML chunk is actually a flight/travel ticket block.

    Returns:
        (is_valid, reason)
    """

    prompt = f"""You are a strict binary classifier.

Task:
Determine whether the following HTML snippet contains an actual flight/travel ticket offer.

Positive examples usually include some real travel fields such as:
- airline
- route / origin / destination
- departure or arrival time
- date
- price
- flight number

Rules:
- Return ONLY valid JSON
- No markdown
- If uncertain, return false
- Keep reason very short (max 10 words)

Required JSON:
{{"is_ticket": true, "reason": "short reason"}}

HTML:
\"\"\"{html_chunk[:MAX_HTML_CHARS]}\"\"\"
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "num_predict": 50
        }
    }

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=(5, REQUEST_TIMEOUT),
        )
        response.raise_for_status()

        result_json = response.json()
        response_text = result_json.get("response", "").strip()

        data = json.loads(response_text)
        is_ticket = bool(data.get("is_ticket", False))
        reason = str(data.get("reason", "no reason")).strip()

        return is_ticket, reason or "no reason"

    except requests.exceptions.RequestException as e:
        return False, f"Ollama API connection error: {str(e)}"
    except json.JSONDecodeError as e:
        return False, f"Failed to parse LLM response: {str(e)}"


if __name__ == "__main__":
    sample_html = """
    <div class="ticket-card">
        <span class="airline">ماهان</span>
        <span class="time">14:30</span>
        <span class="price">15,500,000 ریال</span>
        <span class="route">تهران به مشهد</span>
    </div>
    """

    print("Testing final validation...")
    valid, reason = final_validation(sample_html)
    print(f"Is Valid: {valid}")
    print(f"Reason: {reason}")
