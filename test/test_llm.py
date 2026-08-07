import json
import os
from typing import Tuple
import math
import subprocess
import tempfile

import requests
import subprocess
import time

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/api/generate"
# MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "360"))
MAX_HTML_CHARS = int(os.getenv("FINAL_VALIDATION_MAX_HTML_CHARS", "100000"))

NODE_WORKDIR = os.getcwd()
NODE_PATH = os.path.join(NODE_WORKDIR, "node_modules")

OLLAMA_PROCESS = None


def start_ollama_server():
    global OLLAMA_PROCESS

    if OLLAMA_PROCESS is not None and OLLAMA_PROCESS.poll() is None:
        return True

    OLLAMA_PROCESS = subprocess.Popen(
        ["ollama", "serve"],
        stdout=open("/kaggle/working/ollama_stdout.log", "a"),
        stderr=open("/kaggle/working/ollama_stderr.log", "a"),
    )

    for _ in range(20):
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)

    return False


def clean_html_with_js(html: str) -> str:
    # Safety: cap raw input BEFORE jsdom parses it.
    # jsdom can be memory-heavy on very large/pathological HTML.
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS]

    js_code = r"""

        const fs = require("fs");
        const { JSDOM, VirtualConsole } = require("jsdom");
        
        const inputPath = process.argv[2];
        const html = fs.readFileSync(inputPath, "utf8");
        
        const virtualConsole = new VirtualConsole();
        
        const dom = new JSDOM(html, {
            virtualConsole
        });
        
        const document = dom.window.document;
        const NodeFilter = dom.window.NodeFilter;
        
        const clone = document.documentElement.cloneNode(true);
        
        const REMOVE_TAGS = new Set([
            "svg",
            "symbol",
            "use"
        ]);
        
        function isHiddenElement(el) {
            const style = (el.getAttribute("style") || "")
                .toLowerCase()
                .replace(/\s+/g, "");
        
            return (
                el.hasAttribute("hidden") ||
                el.getAttribute("aria-hidden") === "true" ||
                style.includes("display:none") ||
                style.includes("visibility:hidden")
            );
        }
        
        // Remove HTML comments
        {
            const walker = document.createTreeWalker(
                clone,
                NodeFilter.SHOW_COMMENT
            );
        
            const comments = [];
            while (walker.nextNode()) {
                comments.push(walker.currentNode);
            }
        
            for (const node of comments) {
                node.remove();
            }
        }
        
        // Remove only SVGs and hidden elements
        {
            const elements = Array.from(clone.querySelectorAll("*")).reverse();
        
            for (const el of elements) {
                const tag = el.tagName.toLowerCase();
        
                if (REMOVE_TAGS.has(tag)) {
                    el.remove();
                    continue;
                }
        
                if (isHiddenElement(el)) {
                    el.remove();
                }
            }
        }
        
        process.stdout.write("<!DOCTYPE html>\n" + clone.outerHTML);
        
        
        """

    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as html_file:
        html_file.write(html)
        html_path = html_file.name

    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as js_file:
        js_file.write(js_code)
        js_path = js_file.name

    try:
        result = subprocess.run(
            [
                "node",
                js_path,
                html_path
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=NODE_WORKDIR,
            env={
                **os.environ,
                "NODE_PATH": NODE_PATH,
            },
        )

        return result.stdout

    except subprocess.CalledProcessError as exc:
        print("\nHTML cleaner failed, using original HTML")
        print("STDERR:")
        print(exc.stderr)
        return html

    except subprocess.TimeoutExpired as exc:
        print(f"\nHTML cleaner timeout, using original HTML: {exc}")
        return html

    except Exception as exc:
        print(f"\nHTML cleaner failed, using original HTML: {exc}")
        return html

    finally:
        try:
            os.remove(html_path)
        except OSError:
            pass

        try:
            os.remove(js_path)
        except OSError:
            pass


def final_validation(html_chunk: str) -> Tuple[bool, float]:
    html_chunk = clean_html_with_js(html_chunk)
    # print(html_chunk[:MAX_HTML_CHARS])
    system_rules = """
    You are a strict whole-chunk HTML binary classifier.

    Classify the complete provided HTML chunk, not merely whether some text inside it
    looks like a flight ticket.

    Return exactly one JSON object with exactly these keys:
    {
      "is_ticket": boolean,
      "confidence": number,
      "why": string
    }

    The result must be false if the HTML is a parent section, wrapper, list,
    search-results container, airline filter, or collection containing one or more
    flight-related options.

    Never infer is_ticket=true merely because the chunk contains flight names,
    airlines, times, prices, or a booking button.

    Do not output markdown, explanations outside the JSON, or extra keys.
    """

    prompt = f"""
    Classify whether the following HTML chunk represents exactly ONE complete standalone actionable flight ticket card.

    <rules>
    Return true ONLY if the chunk contains:
    - one airline section
    - route/origin and destination
    - departure or arrival time
    - price
    - actionable/selectable CTA

    Important:
    You do NOT have reliable knowledge of all airline names.
    Do NOT reject a card just because the airline name is unfamiliar.
    Infer whether an airline is present based on layout, structure, positioning, logos, labels, and surrounding flight-related context.

    Return false if ANY apply:
    - Contains multiple ticket cards
    - Contains wrapper/list/container elements
    - Contains banners, ads, hotels, headers, filters, sticky bars, summaries, or unrelated content
    - Is only a partial component
    - One of its child elements is itself a complete valid ticket card
    - Route, timing, airline section, or price is unclear or missing
    - if it contains a ticket card plus any unrelated sibling or external UI section, including filters, result-list controls, headers, banners, ads, pagination, or additional content.


    Responsive mobile/desktop duplicate elements inside the same card do NOT count as multiple cards.
    </rules>

    HTML:
    \"\"\"{html_chunk[:MAX_HTML_CHARS]}\"\"\"
    CRITICAL Reminder:
    Return true ONLY if the chunk contains:airline, route-destination, time, price.
    Return ONLY valid JSON.
    Return false for multiple tickets only when the chunk contains at least two distinct itinerary offers. Multiple nested elements, grid columns, labels, or visual sections do not by themselves indicate multiple cards.
    Return false if it contains a ticket card plus any unrelated sibling or external UI section, including filters, result-list controls, headers, banners, ads, pagination, or additional content.

    Schema:
    {{"is_ticket": <boolean>, "confidence": <float>, "why": "<very short reason>"}}
    """

    estimated_tokens = math.ceil(len(prompt) / 2) + 150
    dynamic_num_ctx = math.ceil(estimated_tokens * 2.6 / 64) * 64
    dynamic_num_ctx = max(8192, min(dynamic_num_ctx, 64000))
    print(dynamic_num_ctx)

    payload = {
        "model": MODEL_NAME,
        "system": system_rules,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        # "keep_alive": "30m",
        "options": {
            "temperature": 0.15,
            "num_predict": 440,
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
        print(data)

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
    if not start_ollama_server():
        raise RuntimeError("Could not start Ollama server.")

    with open("/kaggle/input/datasets/rezapourmoridi/flight-ticket-html/real_dataset_snap_not_tested.json", "r",
              encoding="utf-8") as f:
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