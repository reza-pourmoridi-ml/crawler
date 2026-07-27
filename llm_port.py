#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Discover flight-ticket cards and extract price/agency using Ollama.

Pipeline:
1) Preserve original DOM and create a conservative compact DOM.
2) Split into complete DOM subtrees, never cutting HTML textually.
3) Cheap local scoring selects likely price-containing chunks.
4) Ollama classifies every candidate chunk.
5) Positive regions are used as examples for selector inference.
6) Ollama proposes selectors for ticket-card, price and agency.
7) Selectors are deterministically validated on the original HTML.

The script focuses on:
- one ticket/offer per record
- price
- agency/airline

Debug logs:
    LLM_PORT_DEBUG=1
    LLM_PORT_TRACE_HTML=1

Example:
    docker compose run --rm crawler python llm_port.py

With full prompt/response previews:
    docker compose run --rm \
        -e LLM_PORT_DEBUG=1 \
        -e LLM_PORT_TRACE_HTML=1 \
        crawler python llm_port.py
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Comment, FeatureNotFound, Tag


# ============================================================================
# Configuration
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

INPUT_HTML = Path(
    os.getenv(
        "INPUT_HTML",
        "alibaba_raw_data/20260719_130537_www_snapptrip_ir_flights_THR_city_MHD_city.html",
    )
)

OUTPUT_JSON = Path(
    os.getenv(
        "OUTPUT_JSON",
        "alibaba_raw_data/snapptrip_selectors.json",
    )
)

MAX_MODEL_CHARS = int(os.getenv("MAX_MODEL_CHARS", "12000"))
MAX_CANDIDATE_CHUNKS = int(os.getenv("MAX_CANDIDATE_CHUNKS", "80"))
REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

DEBUG = os.getenv(
    "LLM_PORT_DEBUG",
    "1",
).lower() not in {"0", "false", "no", "off"}

TRACE_HTML = os.getenv(
    "LLM_PORT_TRACE_HTML",
    "0",
).lower() in {"1", "true", "yes", "on"}


# ============================================================================
# Logging helpers
# ============================================================================

def now_stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(message: str) -> None:
    """
    Print an immediate debug message to stderr.
    flush=True is important inside Docker.
    """
    if DEBUG:
        print(
            f"[{now_stamp()}] {message}",
            file=sys.stderr,
            flush=True,
        )


def log_stage(title: str) -> None:
    if DEBUG:
        print(
            f"\n[{now_stamp()}] === {title} ===",
            file=sys.stderr,
            flush=True,
        )


def preview_text(value: Any, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", str(value)).strip()

    if len(value) <= limit:
        return value

    return value[:limit] + "..."


# ============================================================================
# Regular expressions and text helpers
# ============================================================================

PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹",
    "0123456789",
)

ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩",
    "0123456789",
)

PRICE_RE = re.compile(
    r"(?:"
    r"\d[\d,٬.\s]{2,}\s*(?:تومان|ریال|irr|irt)"
    r"|"
    r"(?:تومان|ریال|irr|irt)\s*\d[\d,٬.\s]{2,}"
    r")",
    re.I,
)

NUMBER_RE = re.compile(
    r"\b\d[\d,٬.\s]{2,}\b",
)

TIME_RE = re.compile(
    r"\b(?:[01]?\d|2[0-3])\s*[:：]\s*[0-5]\d\b",
)

IATA_RE = re.compile(
    r"\b[A-Z]{3}\b",
)

PRICE_WORDS = (
    "قیمت",
    "تومان",
    "ریال",
    "خرید",
    "رزرو",
    "بلیط",
    "پرواز",
    "airline",
    "flight",
)


def norm_text(value: str) -> str:
    return (
        value
        .translate(PERSIAN_DIGITS)
        .translate(ARABIC_DIGITS)
        .replace("٬", ",")
        .replace("\u200c", " ")
    )


def make_soup(html: str) -> BeautifulSoup:
    """
    Prefer lxml because it is faster and more tolerant.
    Fall back to Python's built-in html.parser if lxml is unavailable.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
        log("[parse] parser=lxml")
        return soup
    except FeatureNotFound:
        log("[parse] lxml is unavailable; falling back to html.parser")
        return BeautifulSoup(html, "html.parser")


# ============================================================================
# DOM processing
# ============================================================================

def compact_dom(html: str) -> BeautifulSoup:
    log("[compact] parsing HTML for compact DOM")

    soup = make_soup(html)

    comments = soup.find_all(
        string=lambda value: isinstance(value, Comment)
    )

    for node in comments:
        node.extract()

    removable_tags = [
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "canvas",
        "template",
    ]

    removed_count = 0

    for tag in soup.find_all(removable_tags):
        tag.decompose()
        removed_count += 1

    log(f"[compact] removed non-content tags={removed_count}")

    # Keep semantic and useful data attributes.
    keep = {
        "id",
        "class",
        "data-testid",
        "role",
        "aria-label",
        "aria-labelledby",
        "name",
        "title",
        "itemprop",
        "itemtype",
        "itemscope",
        "href",
        "src",
        "alt",
        "value",
    }

    processed_tags = 0
    removed_attributes = 0
    removed_classes = 0

    for tag in soup.find_all(True):
        processed_tags += 1

        for attr in list(tag.attrs):
            if attr not in keep and not attr.startswith("data-"):
                del tag.attrs[attr]
                removed_attributes += 1

        if "class" in tag.attrs:
            original_classes = tag.get("class", [])

            semantic_classes = [
                class_name
                for class_name in original_classes
                if re.search(
                    r"(price|fare|flight|ticket|airline|agency|carrier|"
                    r"offer|result|card|booking|solution)",
                    class_name,
                    re.I,
                )
            ]

            if semantic_classes:
                tag["class"] = semantic_classes
            else:
                tag.attrs.pop("class", None)

            removed_classes += max(
                0,
                len(original_classes) - len(semantic_classes),
            )

    log(
        f"[compact] processed tags={processed_tags:,} | "
        f"removed attributes={removed_attributes:,} | "
        f"removed class tokens={removed_classes:,}"
    )

    return soup


def add_node_ids(soup: BeautifulSoup) -> None:
    tags = soup.find_all(True)

    for index, tag in enumerate(tags):
        tag["data-crawler-node-id"] = f"n{index}"

    log(f"[dom] assigned node IDs={len(tags):,}")


def subtree_size(tag: Tag) -> int:
    return len(str(tag))


def make_chunks(
    root: Tag,
    max_chars: int = MAX_MODEL_CHARS,
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []

    def walk(node: Tag) -> None:
        children = [
            child
            for child in node.find_all(recursive=False)
            if isinstance(child, Tag)
        ]

        if subtree_size(node) <= max_chars or not children:
            text = norm_text(
                node.get_text(" ", strip=True)
            )

            chunks.append(
                {
                    "node_id": node.get("data-crawler-node-id"),
                    "html": str(node),
                    "text": text,
                }
            )
            return

        for child in children:
            walk(child)

    walk(root)

    return chunks


def heuristic_score(chunk: Dict[str, Any]) -> int:
    text = norm_text(chunk["text"])

    score = 0

    if PRICE_RE.search(text):
        score += 6

    if NUMBER_RE.search(text):
        score += 1

    if any(
        word.lower() in text.lower()
        for word in PRICE_WORDS
    ):
        score += 2

    if len(TIME_RE.findall(text)) >= 2:
        score += 1

    if IATA_RE.search(text):
        score += 1

    return score


# ============================================================================
# Ollama communication
# ============================================================================

def ollama_json(
    prompt: str,
    task: str = "unknown",
) -> Dict[str, Any]:
    endpoint = f"{OLLAMA_URL.rstrip('/')}/api/generate"

    log(
        f"[ollama] task={task} | "
        f"model={MODEL} | "
        f"url={endpoint}"
    )

    log(
        f"[ollama] prompt chars={len(prompt):,} | "
        f"timeout={REQUEST_TIMEOUT}s"
    )

    if TRACE_HTML:
        log(
            f"[ollama] prompt preview: "
            f"{preview_text(prompt, 1200)}"
        )

    log("[ollama] waiting for model response...")

    started = time.perf_counter()

    try:
        response = requests.post(
            endpoint,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                },
            },
            timeout=REQUEST_TIMEOUT,
        )

        elapsed = time.perf_counter() - started

        log(
            f"[ollama] HTTP status={response.status_code} | "
            f"elapsed={elapsed:.2f}s"
        )

        response.raise_for_status()

        response_payload = response.json()
        raw = response_payload.get("response", "{}").strip()

        log(
            f"[ollama] raw response chars={len(raw):,}"
        )

        if TRACE_HTML:
            log(
                f"[ollama] raw response preview: "
                f"{preview_text(raw, 1200)}"
            )

        try:
            parsed = json.loads(raw)

            log(
                f"[ollama] JSON parsed successfully | "
                f"keys={list(parsed.keys())}"
            )

            return parsed

        except json.JSONDecodeError:
            log(
                "[ollama] direct JSON parsing failed; "
                "trying to extract JSON object"
            )

            match = re.search(r"\{.*\}", raw, re.S)

            if not match:
                raise ValueError(
                    f"Ollama returned invalid JSON: {raw[:500]}"
                )

            parsed = json.loads(match.group(0))

            log(
                f"[ollama] extracted JSON parsed successfully | "
                f"keys={list(parsed.keys())}"
            )

            return parsed

    except requests.Timeout:
        elapsed = time.perf_counter() - started

        log(
            f"[ollama] TIMEOUT after {elapsed:.2f}s | "
            f"task={task}"
        )

        raise

    except requests.RequestException as error:
        elapsed = time.perf_counter() - started

        log(
            f"[ollama] REQUEST ERROR after {elapsed:.2f}s | "
            f"task={task} | "
            f"{type(error).__name__}: {error}"
        )

        raise

    except Exception as error:
        elapsed = time.perf_counter() - started

        log(
            f"[ollama] ERROR after {elapsed:.2f}s | "
            f"task={task} | "
            f"{type(error).__name__}: {error}"
        )

        raise


def classify_chunk(
    chunk: Dict[str, Any],
    index: int = 0,
    total: int = 0,
    score: int = 0,
) -> Dict[str, Any]:
    node_id = chunk.get("node_id")
    html = chunk.get("html", "")
    text = chunk.get("text", "")

    log(
        f"[classify] chunk {index}/{total} | "
        f"node={node_id} | "
        f"score={score} | "
        f"html_chars={len(html):,} | "
        f"text='{preview_text(text, 180)}'"
    )

    prompt = f"""You inspect one fragment of an HTML document.
Your ONLY target is a repeated travel-ticket/flight-offer record containing a payable price.
The useful fields are only: price and agency/airline. Ignore filters, price ranges, calendars,
SEO, FAQ, JSON-LD base prices, advertisements and navigation.
Do not invent information. Return JSON only with this schema:
{{"contains_ticket_price": true, "confidence": 0.0, "region_type": "ticket|list|filter|calendar|seo|unknown", "evidence": [{{"text":"", "price":"", "agency":""}}]}}
HTML fragment:
{html}
"""

    result = ollama_json(
        prompt,
        task=f"classify_chunk node={node_id}",
    )

    contains_ticket_price = result.get(
        "contains_ticket_price"
    )

    try:
        confidence = float(
            result.get("confidence", 0) or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0

    region_type = result.get("region_type")

    log(
        f"[classify] result node={node_id} | "
        f"contains_ticket_price={contains_ticket_price} | "
        f"confidence={confidence} | "
        f"region_type={region_type}"
    )

    evidence = result.get("evidence") or []

    if evidence:
        log(
            "[classify] evidence="
            + preview_text(
                json.dumps(
                    evidence,
                    ensure_ascii=False,
                ),
                400,
            )
        )

    return result


def selector_prompt(
    positive_html: str,
    negative_html: str,
) -> Dict[str, Any]:
    log_stage("ASK OLLAMA TO INFER CSS SELECTORS")

    log(
        f"[selector] positive HTML chars={len(positive_html):,}"
    )

    log(
        f"[selector] negative HTML chars={len(negative_html):,}"
    )

    prompt = f"""Infer robust CSS selectors from the HTML examples.
A ticket is one repeated offer containing a payable price and an agency/airline name.
Return JSON only:
{{"ticket_selector":"", "price_selector":"", "agency_selector":"", "fallbacks":[], "reason":""}}
Rules: prefer stable data-* / data-testid / semantic attributes; otherwise use meaningful classes.
Never use nth-child, nth-of-type, exact price text, hashed classes, or long Tailwind classes.
The selectors must work relative to each ticket element for price and agency.
POSITIVE EXAMPLES:
{positive_html}
NEGATIVE EXAMPLES:
{negative_html}
"""

    result = ollama_json(
        prompt,
        task="infer_css_selectors",
    )

    log(
        f"[selector] ticket_selector="
        f"{result.get('ticket_selector')!r}"
    )

    log(
        f"[selector] price_selector="
        f"{result.get('price_selector')!r}"
    )

    log(
        f"[selector] agency_selector="
        f"{result.get('agency_selector')!r}"
    )

    log(
        f"[selector] fallbacks="
        f"{preview_text(result.get('fallbacks', []), 500)}"
    )

    log(
        f"[selector] reason="
        f"{preview_text(result.get('reason', ''), 500)}"
    )

    return result


# ============================================================================
# Extraction and validation
# ============================================================================

def digits_and_price(text: str) -> Optional[int]:
    normalized = norm_text(text)

    match = (
        PRICE_RE.search(normalized)
        or NUMBER_RE.search(normalized)
    )

    if not match:
        return None

    digits = re.sub(r"\D", "", match.group(0))

    try:
        return int(digits) if len(digits) >= 3 else None
    except ValueError:
        return None


def validate(
    soup: BeautifulSoup,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    log_stage("VALIDATE SELECTORS ON ORIGINAL HTML")

    card_selector = result.get("ticket_selector", "")
    price_selector = result.get("price_selector", "")
    agency_selector = result.get("agency_selector", "")

    log(
        f"[validate] ticket_selector={card_selector!r}"
    )

    log(
        f"[validate] price_selector={price_selector!r}"
    )

    log(
        f"[validate] agency_selector={agency_selector!r}"
    )

    try:
        cards = (
            soup.select(card_selector)
            if card_selector
            else []
        )
    except Exception as error:
        log(
            f"[validate] bad ticket selector: "
            f"{type(error).__name__}: {error}"
        )

        return {
            "accepted": False,
            "error": f"bad ticket selector: {error}",
        }

    log(
        f"[validate] cards found={len(cards)}"
    )

    valid = 0
    records = []

    for index, card in enumerate(cards, start=1):
        try:
            prices = (
                card.select(price_selector)
                if price_selector
                else []
            )
        except Exception as error:
            log(
                f"[validate] card {index}: "
                f"bad price selector: {error}"
            )
            prices = []

        try:
            agencies = (
                card.select(agency_selector)
                if agency_selector
                else []
            )
        except Exception as error:
            log(
                f"[validate] card {index}: "
                f"bad agency selector: {error}"
            )
            agencies = []

        price_text = " ".join(
            element.get_text(" ", strip=True)
            for element in prices
        )

        agency_text = " ".join(
            element.get_text(" ", strip=True)
            for element in agencies
        )

        price = digits_and_price(price_text)

        is_valid = bool(
            price is not None
            and agency_text.strip()
        )

        if is_valid:
            valid += 1

        log(
            f"[validate] card {index}/{len(cards)} | "
            f"prices={len(prices)} | "
            f"agencies={len(agencies)} | "
            f"price={price} | "
            f"agency='{preview_text(agency_text, 100)}' | "
            f"valid={is_valid}"
        )

        records.append(
            {
                "price": price,
                "price_text": price_text,
                "agency": agency_text.strip(),
            }
        )

    ratio = valid / len(cards) if cards else 0.0

    accepted = (
        len(cards) >= 2
        and ratio >= 0.60
    )

    log(
        f"[validate] accepted={accepted} | "
        f"card_count={len(cards)} | "
        f"valid_count={valid} | "
        f"valid_ratio={ratio:.3f}"
    )

    return {
        "accepted": accepted,
        "card_count": len(cards),
        "valid_count": valid,
        "valid_ratio": round(ratio, 3),
        "records": records,
    }


# ============================================================================
# Main pipeline
# ============================================================================

def main() -> None:
    total_started = time.perf_counter()

    log_stage("START")

    log(f"[config] input={INPUT_HTML}")
    log(f"[config] output={OUTPUT_JSON}")
    log(f"[config] ollama_url={OLLAMA_URL}")
    log(f"[config] model={MODEL}")
    log(f"[config] max_model_chars={MAX_MODEL_CHARS:,}")
    log(f"[config] max_candidate_chunks={MAX_CANDIDATE_CHUNKS}")
    log(f"[config] request_timeout={REQUEST_TIMEOUT}s")
    log(f"[config] debug={DEBUG}")
    log(f"[config] trace_html={TRACE_HTML}")

    # ---------------------------------------------------------------------
    # Read input
    # ---------------------------------------------------------------------

    log_stage("READ INPUT HTML")

    if not INPUT_HTML.exists():
        raise FileNotFoundError(
            f"Input HTML not found: {INPUT_HTML}"
        )

    original = INPUT_HTML.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    log(
        f"[input] original HTML chars={len(original):,}"
    )

    # ---------------------------------------------------------------------
    # Parse original HTML
    # ---------------------------------------------------------------------

    log_stage("PARSE ORIGINAL HTML")

    soup = make_soup(original)

    log("[parse] original soup parsed successfully")

    # ---------------------------------------------------------------------
    # Create compact DOM
    # ---------------------------------------------------------------------

    log_stage("CREATE COMPACT DOM")

    model_soup = compact_dom(original)
    add_node_ids(model_soup)

    log(
        f"[compact] compact HTML chars={len(str(model_soup)):,}"
    )

    body = model_soup.body or model_soup

    # ---------------------------------------------------------------------
    # Make chunks
    # ---------------------------------------------------------------------

    log_stage("MAKE DOM CHUNKS")

    chunks = make_chunks(body)

    log(
        f"[chunks] total chunks={len(chunks):,}"
    )

    if chunks:
        sizes = [
            len(chunk.get("html", ""))
            for chunk in chunks
        ]

        log(
            f"[chunks] min_chars={min(sizes):,} | "
            f"max_chars={max(sizes):,} | "
            f"avg_chars={sum(sizes) // len(sizes):,}"
        )

    # ---------------------------------------------------------------------
    # Heuristic scoring
    # ---------------------------------------------------------------------

    log_stage("HEURISTIC SCORING")

    scored_all = sorted(
        (
            (heuristic_score(chunk), chunk)
            for chunk in chunks
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    score_qualified = [
        item
        for item in scored_all
        if item[0] >= 3
    ]

    scored = score_qualified[:MAX_CANDIDATE_CHUNKS]

    log(
        f"[score] chunks with score>=3="
        f"{len(score_qualified):,}"
    )

    log(
        f"[score] selected candidates="
        f"{len(scored):,}"
    )

    for index, (score, chunk) in enumerate(
        scored[:20],
        start=1,
    ):
        log(
            f"[score] top {index}: "
            f"node={chunk.get('node_id')} | "
            f"score={score} | "
            f"html_chars={len(chunk.get('html', '')):,} | "
            f"text='{preview_text(chunk.get('text', ''), 140)}'"
        )

    # ---------------------------------------------------------------------
    # Classify chunks with Ollama
    # ---------------------------------------------------------------------

    log_stage("CLASSIFY CANDIDATE CHUNKS WITH OLLAMA")

    classifications = []

    for index, (score, chunk) in enumerate(
        scored,
        start=1,
    ):
        try:
            analysis = classify_chunk(
                chunk,
                index=index,
                total=len(scored),
                score=score,
            )

            contains_ticket_price = analysis.get(
                "contains_ticket_price"
            )

            try:
                confidence = float(
                    analysis.get("confidence", 0) or 0
                )
            except (TypeError, ValueError):
                confidence = 0.0

            if (
                contains_ticket_price
                and confidence >= 0.45
            ):
                log(
                    f"[classify] ACCEPT | "
                    f"node={chunk.get('node_id')} | "
                    f"score={score} | "
                    f"confidence={confidence}"
                )

                classifications.append(
                    {
                        "score": score,
                        "chunk": chunk,
                        "analysis": analysis,
                    }
                )
            else:
                log(
                    f"[classify] REJECT | "
                    f"node={chunk.get('node_id')} | "
                    f"contains={contains_ticket_price} | "
                    f"confidence={confidence}"
                )

        except Exception as error:
            print(
                f"WARN chunk {chunk.get('node_id')}: {error}",
                file=sys.stderr,
                flush=True,
            )

            log(
                f"[classify] ERROR | "
                f"node={chunk.get('node_id')} | "
                f"{type(error).__name__}: {error}"
            )

    log(
        f"[classify] positive regions="
        f"{len(classifications):,}"
    )

    if not classifications:
        raise RuntimeError(
            "No likely ticket-price region was found."
        )

    # ---------------------------------------------------------------------
    # Build selector examples
    # ---------------------------------------------------------------------

    log_stage("BUILD POSITIVE AND NEGATIVE EXAMPLES")

    positive = "\n".join(
        item["chunk"]["html"]
        for item in classifications[:8]
    )

    negative = "\n".join(
        item["chunk"]["html"]
        for item in scored[-3:]
    )

    log(
        f"[examples] positive regions used="
        f"{min(len(classifications), 8)}"
    )

    log(
        f"[examples] positive chars="
        f"{len(positive):,}"
    )

    log(
        f"[examples] negative regions used="
        f"{min(len(scored), 3)}"
    )

    log(
        f"[examples] negative chars="
        f"{len(negative):,}"
    )

    # ---------------------------------------------------------------------
    # Infer selectors
    # ---------------------------------------------------------------------

    selectors = selector_prompt(
        positive,
        negative,
    )

    # ---------------------------------------------------------------------
    # Validate selectors
    # ---------------------------------------------------------------------

    validation = validate(
        soup,
        selectors,
    )

    # ---------------------------------------------------------------------
    # Write output
    # ---------------------------------------------------------------------

    log_stage("WRITE OUTPUT JSON")

    output = {
        "input": str(INPUT_HTML),
        "model": MODEL,
        "focus": [
            "ticket",
            "price",
            "agency",
        ],
        "selectors": selectors,
        "validation": validation,
        "classified_regions": [
            {
                "node_id": item["chunk"]["node_id"],
                "score": item["score"],
                "analysis": item["analysis"],
            }
            for item in classifications
        ],
    }

    OUTPUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_JSON.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    elapsed_total = time.perf_counter() - total_started

    log(
        f"[output] written={OUTPUT_JSON}"
    )

    log(
        f"[done] total elapsed={elapsed_total:.2f}s"
    )

    # Final machine-readable result on stdout.
    print(
        json.dumps(
            {
                "output": str(OUTPUT_JSON),
                "selectors": selectors,
                "validation": validation,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("[fatal] interrupted by user")
        sys.exit(130)
    except Exception as error:
        log(
            f"[fatal] {type(error).__name__}: {error}"
        )
        raise
