"""Ported from test-ollama.ipynb; keep the tested algorithms unchanged."""

import json
import re
from bs4 import BeautifulSoup
from difflib import get_close_matches

PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def clean_text_and_normalize(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    text = text.translate(PERSIAN_ARABIC_DIGITS)
    text = re.sub(r'[,\u066C،٬]', '', text)
    return text


def get_price(html: str) -> int:
    text = clean_text_and_normalize(html)
    for num_str in re.findall(r'\d+', text):
        val = int(num_str)
        if 1_000_000 <= val <= 1_000_000_000:
            return val
    return 0


def get_time(html: str):
    text = html.translate(PERSIAN_ARABIC_DIGITS)
    m = re.search(r'\b(?:[0-1]?\d|2[0-3]):[0-5]\d\b', text)
    return m.group(0) if m else ""


def get_full_text(html: str) -> str:
    return clean_text_and_normalize(html)


def get_airline(text: str, THRESHOLD=0.8, *, ALIAS_LOOKUP, ALL_ALIASES_LOWER) -> str:
    text_lower = text.lower()
    tokens = text_lower.split()
    
    # لیستی برای جمع‌آوری تمام احتمالات
    candidates = []

    def check_and_add(phrase):
        # چک کردن دقیق (Direct Match)
        if phrase in ALIAS_LOOKUP:
            candidates.append(ALIAS_LOOKUP[phrase])
            return True
        # چک کردن فازی (Fuzzy Match)
        matches = get_close_matches(phrase, ALL_ALIASES_LOWER, n=1, cutoff=THRESHOLD)
        if matches:
            candidates.append(ALIAS_LOOKUP[matches[0]])
            return True
        return False

    # ۱. جستجوی ۳ کلمه‌ای (اولویت اول - مثل "ایران ایر تور")
    for i in range(len(tokens) - 2):
        check_and_add(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")

    # ۲. جستجوی ۲ کلمه‌ای (اولویت دوم - مثل "کیش ایر")
    for i in range(len(tokens) - 1):
        check_and_add(f"{tokens[i]} {tokens[i+1]}")

    # ۳. جستجوی تک‌کلمه‌ای (اولویت سوم - مثل "ماهان")
    for token in tokens:
        if len(token) >= 3:
            check_and_add(token)

    # انتخاب هوشمندانه:
    # اگر "ایران ایر تور" پیدا شده باشد، در لیست candidates ما [..., "ایران ایرتور", "ایران ایر"] داریم.
    # کافیست لیستی را برگردانیم که بیشترین طول کاراکتری را دارد (چون خاص‌تر است).
    if candidates:
        # برگرداندن آیتمی که نام آن در دیتای اصلی طولانی‌تر است (دقت بالاتر)
        return max(candidates, key=len)
            
    return ""


def extract_ticket_item(item, airlines):
    ALIAS_LOOKUP = {alias.lower(): key for key, aliases in airlines.items() for alias in aliases}
    ALL_ALIASES_LOWER = list(ALIAS_LOOKUP.keys())
    html = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    text = get_full_text(html)
    return {
        "time": get_time(html),
        "price": get_price(html),
        "airline": get_airline(text, ALIAS_LOOKUP=ALIAS_LOOKUP, ALL_ALIASES_LOWER=ALL_ALIASES_LOWER),
        "text": text,
    }
