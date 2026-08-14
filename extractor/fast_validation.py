import os
import re
import json
import difflib
from bs4 import BeautifulSoup
from typing import Tuple

MIN_HTML_LENGTH = 150
MAX_HTML_LENGTH = 100000
PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def clean_text_and_normalize(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    normalized_text = text.translate(PERSIAN_ARABIC_DIGITS)
    normalized_text = re.sub(r'[,،]', '', normalized_text)
    return normalized_text


def price_validation(html: str) -> bool:
    text = clean_text_and_normalize(html)
    numbers = re.findall(r'\b\d+\b', text)

    for num_str in numbers:
        try:
            val = int(num_str)
            if 1_000_000 <= val <= 1_000_000_000:
                return True
        except ValueError:
            continue

    return False


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
        return {"full": False, "length": length_valid}

    time = time_validation(html)
    if not time:
        return {"full": False, "length": length_valid}

    return {"full": True, "length": length_valid}
