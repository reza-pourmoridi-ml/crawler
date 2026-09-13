"""Ported from test-ollama.ipynb; keep the tested algorithms unchanged."""

import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Tuple

import requests
from bs4 import BeautifulSoup, Tag
try:
    from tqdm import tqdm
except ImportError:  # Progress output is optional in minimal worker environments.
    def tqdm(iterable, **_kwargs):
        return iterable

from app.infra.config import settings

OLLAMA_BASE_URL = settings.ollama_host.rstrip("/")
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/api/generate"
MODEL_NAME = settings.ollama_model
REQUEST_TIMEOUT = settings.ollama_timeout
MAX_HTML_CHARS = settings.final_validation_max_html_chars
NODE_WORKDIR = str(Path(__file__).resolve().parents[2])
NODE_PATH = os.getenv("NODE_PATH", os.path.join(NODE_WORKDIR, "node_modules"))
PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def clean_text_and_normalize(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text(separator=" ")
    text = text.translate(PERSIAN_ARABIC_DIGITS)
    text = re.sub(r"[,\u066C،٬]", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_dom_layers(html: str) -> List[str]:
    """
    دقیقاً یک لایه به داخل قطعه HTML ورودی می‌رود و تمام فرزندان مستقیمی
    که خودشان والد هستند (حداقل یک تگ فرزند دارند) را همراه با تمام زیرمجموعه‌شان
    به عنوان رشته‌های HTML مجزا برمی‌گرداند.
    """
    if not isinstance(html, str):
        raise TypeError("html باید از نوع str باشد.")

    soup = BeautifulSoup(html, "html.parser")
    top_level_tags = [node for node in soup.contents if isinstance(node, Tag)]

    if not top_level_tags:
        return []

    parents_html = []

    for root_tag in top_level_tags:
        for child in root_tag.children:
            if isinstance(child, Tag):
                # بررسی اینکه آیا این فرزند خودش والد است (حداقل یک فرزند تگی دارد)
                has_child_tag = any(isinstance(c, Tag) for c in child.children)
                if has_child_tag:
                    parents_html.append(str(child))

    return parents_html


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


def final_kill_process(html: str) -> bool:
    text = clean_text_and_normalize(html)
    numbers = re.findall(r'\d+', text)

    counter = 0
    for num_str in numbers:
        try:
            val = int(num_str)
            if 1_000_000 <= val <= 1_000_000_000:
                counter += 1
        except ValueError:
            continue

    return counter < 1


def final_validation(html_chunk: str)  -> Tuple[bool, float]:

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
    dynamic_num_ctx = math.ceil(estimated_tokens*2.6 / 64) * 64
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


def save_validated_tickets(
    tickets,
    output_dir,
    output_filename,
):
    """
    ذخیره بلیت‌های تأییدشده در پوشه خروجی.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / output_filename

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            tickets,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def process_file_validation(
    file_path,
    file_number,
    output_dir="storage/temp/validated_tickets",
    on_validated_ticket: Callable[[str], None] | None = None,
):
    """
    یک فایل final_layers را پردازش می‌کند و خروجی متناظر آن را می‌سازد.
    """

    file_path = Path(file_path)

    with file_path.open("r", encoding="utf-8") as f:
        current_layers = json.load(f)

    if not isinstance(current_layers, list):
        raise ValueError(
            f"ساختار فایل {file_path.name} باید یک لیست JSON باشد."
        )

    validated_tickets = []
    layer_count = 1

    while current_layers:
        next_layers = []

        progress_description = (
            f"{file_path.stem} | layer {layer_count}"
        )

        for chunk in tqdm(
            current_layers,
            desc=progress_description,
            unit="chunk",
            leave=False,
        ):
            if not isinstance(chunk, str):
                continue
            if final_kill_process(chunk):
                continue
            try:
                is_ticket, confidence = final_validation(chunk)
            except Exception:
                is_ticket, confidence = False, 0.0

            if is_ticket:
                validated_tickets.append(chunk)
                if on_validated_ticket is not None:
                    on_validated_ticket(chunk)
            else:
                children = extract_dom_layers(chunk)
                if children:
                    next_layers.extend(children)
        if not next_layers:
            break

        current_layers = next_layers
        layer_count += 1

    # حذف duplicateهای احتمالی، بدون تغییر ترتیب
    validated_tickets = list(dict.fromkeys(validated_tickets))

    output_filename = (
        f"validated_tickets_{file_number:03d}.json"
    )

    output_path = save_validated_tickets(
        tickets=validated_tickets,
        output_dir=output_dir,
        output_filename=output_filename,
    )

    return {
        "input_file": file_path.name,
        "output_file": output_path.name,
        "tickets": len(validated_tickets),
        "output_path": str(output_path),
    }
