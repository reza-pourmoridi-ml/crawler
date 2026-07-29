import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Comment


# ============================================================================
# Configuration
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

DATASET_JSON = Path(
    os.getenv(
        "DATASET_JSON",
        "test/dataset.json",
    )
)

OUTPUT_JSON = Path(
    os.getenv(
        "OUTPUT_JSON",
        "llm_eval_results.json",
    )
)

REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
MAX_MODEL_CHARS = int(os.getenv("MAX_MODEL_CHARS", "12000"))
MAX_TEXT_PREVIEW_CHARS = int(os.getenv("MAX_TEXT_PREVIEW_CHARS", "1200"))
SLEEP_BETWEEN_REQUESTS = float(os.getenv("SLEEP_BETWEEN_REQUESTS", "0.0"))

DEBUG = os.getenv(
    "LLM_PORT_DEBUG",
    "1",
).lower() not in {"0", "false", "no", "off"}

USE_MODEL_FOR_BORDERLINE = os.getenv(
    "USE_MODEL_FOR_BORDERLINE",
    "1",
).lower() not in {"0", "false", "no", "off"}


# ============================================================================
# Utilities
# ============================================================================

def debug(msg: str) -> None:
    if DEBUG:
        print(msg)


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Dataset JSON must be a list of objects")

    return data


def to_bool_label(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y"}:
            return True
        if v in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"Cannot convert label to bool: {value!r}")


def get_dataset_fields(item: Dict[str, Any]) -> Tuple[str, bool, str]:
    sample_id = str(item.get("id") or item.get("sample_id") or item.get("uuid") or "")

    html = (
        item.get("html")
        or item.get("html_snippet")
        or item.get("snippet")
        or item.get("dom")
        or ""
    )

    if not isinstance(html, str) or not html.strip():
        raise ValueError(f"Sample {sample_id!r}: html/snippet field missing or empty")

    label_raw = None
    for key in ["is_flight_card", "label", "target", "is_valid", "valid"]:
        if key in item:
            label_raw = item[key]
            break

    if label_raw is None:
        raise ValueError(f"Sample {sample_id!r}: label field missing")

    label = to_bool_label(label_raw)

    if not sample_id:
        sample_id = f"sample_{abs(hash(html)) % 10_000_000}"

    return sample_id, label, html


# ============================================================================
# HTML Cleaning
# ============================================================================

def normalize_html(html: str) -> str:
    if not html or not isinstance(html, str):
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html[:MAX_MODEL_CHARS]

    for tag_name in ["script", "style", "noscript", "svg", "template", "meta", "link"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for c in soup.find_all(string=lambda text: isinstance(text, Comment)):
        c.extract()

    cleaned = str(soup)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > MAX_MODEL_CHARS:
        cleaned = cleaned[:MAX_MODEL_CHARS]

    return cleaned


def extract_visible_text(html: str) -> str:
    if not html:
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = html

    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > MAX_TEXT_PREVIEW_CHARS:
        text = text[:MAX_TEXT_PREVIEW_CHARS]

    return text


# ============================================================================
# Feature Extraction
# ============================================================================

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"

DIGIT_TRANS = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    EN_DIGITS + EN_DIGITS
)


def normalize_digits(text: str) -> str:
    return text.translate(DIGIT_TRANS)


PRICE_PATTERNS = [
    r"\b\d{1,3}(?:,\d{3})+\s*(?:تومان|ریال)\b",
    r"\b\d{6,9}\s*(?:تومان|ریال)\b",
    r"(?:قیمت|مبلغ|کرایه|نرخ)[^\.:\n]{0,20}\d",
]

TIME_PATTERNS = [
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
]

AGENCY_HINT_PATTERNS = [
    r"آژانس",
    r"فروشنده",
    r"ارائه(?:\s*دهنده|\s*کننده)?",
    r"تامین(?:\s*کننده)?",
    r"provider",
    r"seller",
    r"agency",
]

NEGATIVE_PATTERNS = {
    "filter_or_sidebar": [
        r"فیلتر",
        r"مرتب[\s‌-]*سازی",
        r"sidebar",
        r"toolbar",
        r"sort",
    ],
    "sticky_or_summary": [
        r"sticky",
        r"summary",
        r"کمترین قیمت",
        r"نمایش \d+ نتیجه",
        r"حرکت[\w\s‌-]*موجود",
    ],
    "ad_or_promo": [
        r"پیشنهاد ویژه",
        r"تخفیف",
        r"promo",
        r"banner",
        r"recommended",
        r"تور",
    ],
    "non_flight_product": [
        r"هتل",
        r"قطار",
        r"بیمه",
        r"تور",
        r"اتوبوس",
    ],
}

POSITIVE_HINT_PATTERNS = [
    r"پرواز",
    r"flight",
    r"بار مجاز",
    r"باقی[\s‌-]*مانده",
    r"شماره پرواز",
    r"flight[\s‌-]*number",
    r"اکونومی",
    r"بیزینس",
    r"بدون توقف",
]


def count_matches(patterns: List[str], text: str) -> int:
    total = 0
    for p in patterns:
        matches = re.findall(p, text, flags=re.IGNORECASE)
        total += len(matches)
    return total


def has_any(patterns: List[str], text: str) -> bool:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return True
    return False


def extract_features(cleaned_html: str) -> Dict[str, Any]:
    visible_text = extract_visible_text(cleaned_html)
    norm_text = normalize_digits(visible_text)
    norm_html = normalize_digits(cleaned_html)

    price_count = count_matches(PRICE_PATTERNS, norm_text)
    time_count = count_matches(TIME_PATTERNS, norm_text)
    agency_hint_count = count_matches(AGENCY_HINT_PATTERNS, norm_text)

    has_price = price_count > 0
    has_time = time_count > 0
    has_agency = agency_hint_count > 0

    negative_hits = {
        key: has_any(patterns, norm_text + " " + norm_html)
        for key, patterns in NEGATIVE_PATTERNS.items()
    }

    positive_hint_count = count_matches(POSITIVE_HINT_PATTERNS, norm_text + " " + norm_html)

    # تخمین wrapper / multi-card
    # اگر قیمت و زمان و آژانس چندبار تکرار شده باشند، احتمال wrapper بالاست
    probable_multi_card = (
        price_count >= 2 and time_count >= 3
    )

    # وجود چند دکمه/لینک خرید هم می‌تواند نشانه wrapper باشد
    action_words = re.findall(
        r"(?:خرید|رزرو|انتخاب|ادامه خرید|مشاهده جزئیات|reserve|buy|select)",
        norm_text,
        flags=re.IGNORECASE,
    )
    action_count = len(action_words)

    if action_count >= 2 and price_count >= 2:
        probable_multi_card = True

    # اگر متن خیلی کلی و توضیحی باشد
    text_heavy_info = (
        len(norm_text) > 250
        and positive_hint_count == 0
        and has_any([r"راهنما", r"بهترین", r"معمولاً", r"ممکن است"], norm_text)
    )

    # اگر نشانه‌های واضح منفی وجود دارد
    obvious_negative = (
        negative_hits["filter_or_sidebar"]
        or negative_hits["sticky_or_summary"]
        or negative_hits["ad_or_promo"]
        or negative_hits["non_flight_product"]
        or text_heavy_info
    )

    # سیگنال مثبت خام
    has_required_three = has_price and has_time and has_agency

    # single card heuristic
    single_card_likely = has_required_three and not probable_multi_card and not obvious_negative

    return {
        "visible_text_preview": norm_text[:MAX_TEXT_PREVIEW_CHARS],
        "has_price": has_price,
        "has_time": has_time,
        "has_agency": has_agency,
        "price_count": price_count,
        "time_count": time_count,
        "agency_hint_count": agency_hint_count,
        "positive_hint_count": positive_hint_count,
        "action_count": action_count,
        "probable_multi_card": probable_multi_card,
        "obvious_negative": obvious_negative,
        "negative_hits": negative_hits,
        "single_card_likely": single_card_likely,
        "has_required_three": has_required_three,
        "text_heavy_info": text_heavy_info,
    }


# ============================================================================
# Heuristic Decision
# ============================================================================

def heuristic_decision(features: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    """
    خروجی:
      - True/False اگر heuristic مطمئن باشد
      - None اگر مورد borderline باشد و مدل باید تصمیم بگیرد
    """

    if not features["has_price"]:
        return False, "رد شد: قیمت پیدا نشد."
    if not features["has_time"]:
        return False, "رد شد: زمان پرواز پیدا نشد."
    if not features["has_agency"]:
        return False, "رد شد: نام آژانس/فروشنده پیدا نشد."

    if features["negative_hits"]["non_flight_product"]:
        return False, "رد شد: محتوای غیرپروازی مثل هتل/تور/قطار/بیمه دیده شد."

    if features["negative_hits"]["filter_or_sidebar"]:
        return False, "رد شد: شبیه فیلتر/سایدبار/مرتب‌سازی است."

    if features["negative_hits"]["sticky_or_summary"]:
        return False, "رد شد: شبیه summary/sticky/container است."

    if features["negative_hits"]["ad_or_promo"]:
        return False, "رد شد: شبیه تبلیغ/پیشنهاد ویژه است."

    if features["text_heavy_info"]:
        return False, "رد شد: شبیه متن راهنما/اطلاعات کلی است."

    if features["probable_multi_card"]:
        return False, "رد شد: احتمال زیاد wrapper چندکارتی است."

    if features["single_card_likely"]:
        return None, "کاندید مناسب است؛ برای تصمیم نهایی به مدل ارسال می‌شود."

    return False, "رد شد: با وجود برخی سیگنال‌ها، شبیه یک کارت پرواز واحد نیست."


# ============================================================================
# Prompt / Model
# ============================================================================

def build_prompt_from_features(features: Dict[str, Any]) -> str:
    # فشرده‌سازی negative_hits به یک پرچم ساده
    neg = features.get("negative_hits", {}) or {}
    negative_summary = {
        "non_flight": bool(neg.get("non_flight_product")),
        "ui_wrapper": bool(neg.get("filter_or_sidebar") or neg.get("sticky_or_summary")),
        "ad_or_promo": bool(neg.get("ad_or_promo")),
    }

    preview = (features.get("visible_text_preview") or "")[:500]

    return f"""
You validate flight result snippets.

Return TRUE if it most likely describes ONE flight card and:
- has_price is true
- has_time is true
- has_agency is true
and there is no strong wrapper/non-flight signal.

Return FALSE otherwise.

Reply with only:
TRUE
or
FALSE

Summary:
has_price={features['has_price']}
has_time={features['has_time']}
has_agency={features['has_agency']}
multi_card_suspect={features['probable_multi_card']}
negative_summary={json.dumps(negative_summary, ensure_ascii=False)}

Text preview:
{preview}
""".strip()


def parse_bool_from_text(text: str) -> Optional[bool]:
    if not text:
        return None

    t = text.strip().upper()

    if t == "TRUE":
        return True
    if t == "FALSE":
        return False

    # fallback
    if re.search(r"\bTRUE\b", t):
        return True
    if re.search(r"\bFALSE\b", t):
        return False

    return None


def call_ollama_binary(prompt: str) -> Dict[str, Any]:
    url = f"{OLLAMA_URL.rstrip('/')}/api/generate"
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 5,
        },
    }

    resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    response_text = data.get("response", "").strip()
    parsed_bool = parse_bool_from_text(response_text)

    return {
        "raw_response": response_text,
        "parsed_bool": parsed_bool,
    }


# ============================================================================
# Metrics / Reporting
# ============================================================================

def compute_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    tp = fp = tn = fn = 0
    invalid_model_output = 0

    for r in rows:
        gt = r["ground_truth"]
        pred = r["predicted_label"]

        if pred is None:
            invalid_model_output += 1
            pred = False

        if gt is True and pred is True:
            tp += 1
        elif gt is False and pred is True:
            fp += 1
        elif gt is False and pred is False:
            tn += 1
        elif gt is True and pred is False:
            fn += 1

    total = tp + fp + tn + fn

    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "total": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "invalid_model_output_count": invalid_model_output,
    }


def print_metrics(metrics: Dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("نتیجه‌ی ارزیابی".center(72))
    print("=" * 72)
    print(f"کل نمونه‌ها                    : {metrics['total']}")
    print(f"درستِ مثبت (TP)                : {metrics['tp']}")
    print(f"مثبتِ اشتباه (FP)              : {metrics['fp']}")
    print(f"درستِ منفی (TN)                : {metrics['tn']}")
    print(f"منفیِ اشتباه (FN)              : {metrics['fn']}")
    print(f"خروجی نامعتبر مدل              : {metrics['invalid_model_output_count']}")
    print("-" * 72)
    print(f"Accuracy / دقت کلی             : {metrics['accuracy']:.4f}")
    print(f"Precision / دقت مثبت‌ها        : {metrics['precision']:.4f}")
    print(f"Recall / پوشش مثبت‌ها          : {metrics['recall']:.4f}")
    print(f"F1 / میانگین هارمونیک          : {metrics['f1']:.4f}")
    print("=" * 72 + "\n")


def short_label(v: Optional[bool]) -> str:
    if v is True:
        return "کارت پرواز"
    if v is False:
        return "غیر کارت"
    return "نامشخص"


def print_sample_result(row: Dict[str, Any], idx: int, total: int) -> None:
    status = "✅ درست" if row["correct"] else "❌ غلط"
    source = row["decision_source"]
    gt = "کارت پرواز" if row["ground_truth"] else "غیر کارت"
    pred = short_label(row["predicted_label"])

    print(f"[{idx}/{total}] نمونه: {row['id']}")
    print(f"  - برچسب واقعی      : {gt}")
    print(f"  - پیش‌بینی         : {pred}")
    print(f"  - نتیجه            : {status}")
    print(f"  - منبع تصمیم       : {source}")
    print(f"  - توضیح            : {row['decision_reason']}")
    print(f"  - سیگنال‌ها        : price={row['features']['has_price']}, time={row['features']['has_time']}, agency={row['features']['has_agency']}, multi={row['features']['probable_multi_card']}, negative={row['features']['obvious_negative']}")
    if row.get("model_raw_response") is not None:
        print(f"  - پاسخ خام مدل     : {row['model_raw_response']}")
    if row.get("error"):
        print(f"  - خطا              : {row['error']}")
    print()


def build_human_summary(results: List[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
    false_positives = [r for r in results if r["ground_truth"] is False and r["predicted_label"] is True]
    false_negatives = [r for r in results if r["ground_truth"] is True and r["predicted_label"] is False]
    invalids = [r for r in results if r["predicted_label"] is None]

    return {
        "جمع‌بندی": {
            "کل نمونه‌ها": metrics["total"],
            "تعداد مثبت درست": metrics["tp"],
            "تعداد مثبت اشتباه": metrics["fp"],
            "تعداد منفی درست": metrics["tn"],
            "تعداد منفی اشتباه": metrics["fn"],
            "تعداد خروجی نامعتبر مدل": metrics["invalid_model_output_count"],
            "دقت کلی": round(metrics["accuracy"], 4),
            "دقت مثبت‌ها": round(metrics["precision"], 4),
            "پوشش مثبت‌ها": round(metrics["recall"], 4),
            "امتیاز F1": round(metrics["f1"], 4),
        },
        "توضیح": (
            "برای این مسئله، false positive مهم‌تر از false negative است. "
            "اگر دقت مثبت‌ها (Precision) پایین باشد، مدل هنوز برای validator نهایی قابل اتکا نیست."
        ),
        "نمونه‌های مثبت اشتباه": [
            {
                "id": r["id"],
                "توضیح": r["decision_reason"],
                "پاسخ مدل": r.get("model_raw_response"),
                "متن خلاصه": r["features"]["visible_text_preview"][:300],
            }
            for r in false_positives[:10]
        ],
        "نمونه‌های منفی اشتباه": [
            {
                "id": r["id"],
                "توضیح": r["decision_reason"],
                "پاسخ مدل": r.get("model_raw_response"),
                "متن خلاصه": r["features"]["visible_text_preview"][:300],
            }
            for r in false_negatives[:10]
        ],
        "خروجی‌های نامعتبر مدل": [
            {
                "id": r["id"],
                "پاسخ خام": r.get("model_raw_response"),
            }
            for r in invalids[:10]
        ],
    }


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    dataset = load_dataset(DATASET_JSON)
    debug(f"Loaded dataset: {len(dataset)} samples")

    results: List[Dict[str, Any]] = []

    print("\nشروع ارزیابی مدل...\n")

    for idx, item in enumerate(dataset, start=1):
        sample_id, ground_truth, html = get_dataset_fields(item)
        cleaned_html = normalize_html(html)
        features = extract_features(cleaned_html)

        predicted_label: Optional[bool] = None
        error = None
        model_raw_response = None
        decision_source = "heuristic"
        decision_reason = ""
        model_prompt = None

        try:
            heuristic_label, heuristic_reason = heuristic_decision(features)
            decision_reason = heuristic_reason

            if heuristic_label is not None:
                predicted_label = heuristic_label
                decision_source = "heuristic"
            else:
                if USE_MODEL_FOR_BORDERLINE:
                    model_prompt = build_prompt_from_features(features)
                    model_result = call_ollama_binary(model_prompt)
                    model_raw_response = model_result["raw_response"]
                    predicted_label = model_result["parsed_bool"]
                    decision_source = "model_after_heuristic"

                    if predicted_label is True:
                        decision_reason = "مدل پس از دیدن خلاصه‌ی ویژگی‌ها، نمونه را یک کارت پرواز واحد تشخیص داد."
                    elif predicted_label is False:
                        decision_reason = "مدل پس از دیدن خلاصه‌ی ویژگی‌ها، نمونه را کارت پرواز معتبر تشخیص نداد."
                    else:
                        decision_reason = "مدل خروجی قابل‌فهم TRUE/FALSE نداد."
                else:
                    predicted_label = False
                    decision_source = "heuristic_fallback"
                    decision_reason = "نمونه borderline بود ولی استفاده از مدل غیرفعال است؛ برای احتیاط false شد."

        except Exception as e:
            error = str(e)
            predicted_label = False
            decision_source = "error_fallback"
            decision_reason = "به‌دلیل خطا در پردازش یا فراخوانی مدل، برای احتیاط false شد."

        row = {
            "id": sample_id,
            "ground_truth": ground_truth,
            "predicted_label": predicted_label,
            "correct": (predicted_label == ground_truth) if predicted_label is not None else False,
            "decision_source": decision_source,
            "decision_reason": decision_reason,
            "error": error,
            "model_raw_response": model_raw_response,
            "model_prompt": model_prompt,
            "features": features,
            "html_preview": cleaned_html[:1500],
        }

        results.append(row)
        print_sample_result(row, idx, len(dataset))

        if SLEEP_BETWEEN_REQUESTS > 0:
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    metrics = compute_metrics(results)
    print_metrics(metrics)

    human_summary = build_human_summary(results, metrics)

    output = {
        "config": {
            "ollama_url": OLLAMA_URL,
            "model": MODEL,
            "dataset_json": str(DATASET_JSON),
            "request_timeout": REQUEST_TIMEOUT,
            "max_model_chars": MAX_MODEL_CHARS,
            "max_text_preview_chars": MAX_TEXT_PREVIEW_CHARS,
            "sleep_between_requests": SLEEP_BETWEEN_REQUESTS,
            "use_model_for_borderline": USE_MODEL_FOR_BORDERLINE,
        },
        "metrics": metrics,
        "human_summary": human_summary,
        "results": results,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"فایل نتایج ذخیره شد: {OUTPUT_JSON}\n")


if __name__ == "__main__":
    main()
