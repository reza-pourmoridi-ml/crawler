"""Ported from test-ollama.ipynb; keep the tested algorithms unchanged."""

import json
import re
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup, Tag

MIN_HTML_LENGTH = 150
MAX_HTML_LENGTH = 100000
PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def save_final_layers(final_layers, filename="final_layers.json", folder_name="processed_layers"):
    output_dir = Path(folder_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / filename

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            final_layers,
            file,
            ensure_ascii=False,
            indent=2
        )

    return str(output_path)


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
                has_child_tag = any(isinstance(c, Tag) for c in child.children)
                if has_child_tag:
                    parents_html.append(str(child))

    return parents_html


def clean_text_and_normalize(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    normalized_text = text.translate(PERSIAN_ARABIC_DIGITS)
    normalized_text = re.sub(r'[,\u066C،٬]', '', normalized_text)
    return normalized_text


def price_validation(html: str) -> bool:
    text = clean_text_and_normalize(html)
    numbers = re.findall(r'\d+', text)

    for num_str in numbers:
        try:
            val = int(num_str)
            if 1_000_000 <= val <= 1_000_000_000:
                return True
        except ValueError:
            continue

    return False


def kill_process(html: str) -> bool:
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

    return counter <= 4


def time_validation(html: str) -> bool:
    normalized_html = html.translate(PERSIAN_ARABIC_DIGITS)
    time_pattern = r'\b(?:[0-1]?[0-9]|2[0-3]):[0-5][0-9]\b'
    if re.search(time_pattern, normalized_html):
        return True
    return False


def hot_validate_html(html: str):
    html_len = len(html)
    length_valid = MIN_HTML_LENGTH <= html_len <= MAX_HTML_LENGTH

    price = price_validation(html)
    if not price:
        return {"price": False,"time": "", "length": length_valid}

    time = time_validation(html)
    if not time:
        return {"price": True, "time": False, "length": length_valid}

    return {"price": True,"time": True, "length": length_valid}


def fast_safe_extraction(
    file_path,
    number,
    output_prefix="final_layers",
    folder_name="processed_layers"
):
    """
    یک فایل HTML را پردازش می‌کند و لایه‌های احتمالی کارت پرواز
    را در یک پوشه اختصاصی ذخیره می‌کند (بدون نمایش پروسه داخلی).
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"فایل در مسیر مشخص‌شده یافت نشد: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"مسیر داده‌شده یک فایل نیست: {file_path}")

    html = file_path.read_text(encoding="utf-8")

    current_layers = extract_dom_layers(html)

    final_layers = []
    layer_number = 1
    total_checked = 0

    while current_layers:
        next_layers = []

        for chunk in current_layers:
            total_checked += 1

            if not isinstance(chunk, str) or not chunk.strip():
                continue

            check = hot_validate_html(chunk)

            has_price = check["price"] is True
            has_time = check["time"] is True
            valid_length = check["length"] is True

            if has_price and has_time and valid_length:
                if kill_process(chunk):
                    final_layers.append(chunk)
                else:
                    children = extract_dom_layers(chunk)
                    if children:
                        next_layers.extend(children)
            else:
                children = extract_dom_layers(chunk)
                if children:
                    next_layers.extend(children)

        if not next_layers:
            break

        current_layers = next_layers
        layer_number += 1

    unique_final_layers = list(dict.fromkeys(final_layers))
    
    output_filename = f"{output_prefix}_{number:03d}.json"

    output_path = save_final_layers(
        unique_final_layers,
        filename=output_filename,
        folder_name=folder_name
    )

    print(
        f"✅ File {number}: {file_path.name} | "
        f"Found: {len(unique_final_layers)} | "
        f"Saved to: {folder_name}/{output_filename}"
    )

    return {
        "input_file": str(file_path),
        "input_name": file_path.name,
        "output_file": output_path,
        "tickets_found": len(unique_final_layers),
        "chunks_checked": total_checked,
        "layers_processed": layer_number
    }
