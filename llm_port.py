import os
import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")

def ask_ollama(prompt, model="llama3.2:3b"):
    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False
        },
        timeout=300
    )
    r.raise_for_status()
    return r.json()["response"]

with open("alibaba_raw_data/20260718_105200_www_flytoday_ir_flight_search_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

prompt = f"""
سلام
"""

print(ask_ollama(prompt))
