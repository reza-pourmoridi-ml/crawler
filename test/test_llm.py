import json
import os
from typing import Tuple
import math

import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/")
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "360"))
MAX_HTML_CHARS = int(os.getenv("FINAL_VALIDATION_MAX_HTML_CHARS", "5000"))


def final_validation(html_chunk: str)  -> Tuple[bool, float]:

    prompt = f"""You are a strict binary classifier. Be skeptical: default toward false unless the HTML clearly matches one complete ticket card.

    Task:
    Identify ONLY a single, complete, and actionable individual flight ticket card with airline name.

    CRITICAL RULES (Return false if any apply):
    - If the HTML is a list of multiple tickets (wrapper), return false.
    - If the HTML is a summary, sticky footer, header, or filter box, return false.
    - If it is missing a clear provider/agency name, return false.
    - If it is a generic "search result" or "advertisement" that doesn't represent a specific, selectable flight offer, return false.
    - If layout is ambiguous, partial, or could be a container — return false.
    - If airline, route, time, or price are missing or unclear — return false.
    - if it is a flight ticket but the specific airline name is missing, return false.

    Positive examples MUST include:
    - A specific flight offer with Airline, Route, Time, and Price.

    Confidence:
    - High (0.8–1.0) only when all positive criteria are clearly satisfied.
    - Lower confidence when uncertain; pair low confidence with is_ticket false when skeptical.

    Rules:
    - Return ONLY valid JSON
    - No markdown

    Required JSON:
    {{"is_ticket": true, "confidence": 0.85}}

    HTML:
    \"\"\"{html_chunk[:MAX_HTML_CHARS]}\"\"\"
    """

    estimated_tokens = math.ceil(len(prompt) / 2) + 10
    dynamic_num_ctx = math.ceil(estimated_tokens / 64) * 64
    dynamic_num_ctx = max(512, min(dynamic_num_ctx, 8192))
    print(dynamic_num_ctx)
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.3,
            "num_predict": 30,
            "num_ctx": dynamic_num_ctx
        }
    }

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=(5, REQUEST_TIMEOUT),
        )
        response.raise_for_status()

    except requests.exceptions.Timeout as exc:
        print(f"\nOllama timeout: {exc}")
        return False, 0.0

    except requests.exceptions.RequestException as exc:
        print(f"\nOllama request failed: {exc}")
        return False, 0.0

    try:
        result_json = response.json()
        response_text = result_json.get("response", "").strip()
        data = json.loads(response_text)

    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        print(f"\nInvalid Ollama response: {exc}")
        return False, 0.0

    is_ticket = bool(data.get("is_ticket", False))

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    return is_ticket, confidence



if __name__ == "__main__":
    with open("test/real_dataset_mrblit.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    correct_count = 0
    print(f"{'ID':<25} | {'Expected':<10} | {'Predicted':<10} | {'Confidence':<10} | {'Status'}")
    print("-" * 80)

    for item in dataset:
        is_valid, confidence = final_validation(item["html"])
        expected = item["is_flight_card"]
        passed = (is_valid == expected)

        if passed:
            correct_count += 1

        print(
            f"{item['id']:<25} | {str(expected):<10} | {str(is_valid):<10} | "
            f"{confidence:<10.2f} | {'✅' if passed else '❌'}"
        )

    print("-" * 80)
    print(f"Total: {len(dataset)} | Accuracy: {correct_count / len(dataset):.1%}")
