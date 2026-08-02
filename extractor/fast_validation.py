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
    """استخراج متن‌های ساده از HTML و یکسان‌سازی اعداد و فواصل."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    # تبدیل اعداد فارسی/عربی به انگلیسی
    normalized_text = text.translate(PERSIAN_ARABIC_DIGITS)
    # حذف کاما و ویرگول‌ها برای خواندن راحت‌تر اعداد
    normalized_text = re.sub(r'[,،]', '', normalized_text)
    return normalized_text


def price_validation(html: str) -> bool:
    """بررسی وجود قیمت بین ۱,۰۰۰,۰۰۰ تا ۱,۰۰۰,۰۰۰,۰۰۰ ریال یا تومان."""
    text = clean_text_and_normalize(html)

    # پیدا کردن اعداد پیوسته در متن
    numbers = re.findall(r'\b\d+\b', text)

    for num_str in numbers:
        try:
            val = int(num_str)
            if 1_000_000 <= val <= 1_000_000_000:
                # بررسی اینکه آیا کلمات مربوط به قیمت در نزدیکی عدد هستند یا خیر (اختیاری اما کمک‌کننده)
                return True
        except ValueError:
            continue

    return False


def time_validation(html: str) -> bool:
    """بررسی وجود فرمت زمانی ساعت (مانند 13:45 یا ۱۳:۴۵)."""
    # در این بخش از html خام استفاده می‌کنیم تا ساختار زمان با اعمال clean_text خراب نشود
    normalized_html = html.translate(PERSIAN_ARABIC_DIGITS)

    # الگوی ساعت ۲۴ ساعته: از 00:00 تا 23:59
    time_pattern = r'\b(?:[0-1]?[0-9]|2[0-3]):[0-5][0-9]\b'

    if re.search(time_pattern, normalized_html):
        return True
    return False


def agency_validation(html: str) -> bool:
    """بررسی وجود نام‌های مشابه با لیست ایرلاین‌ها در airlines.json."""
    json_path = "airlines.json"
    if not os.path.exists(json_path):
        # در صورتی که فایل هنوز ساخته نشده باشد
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            airlines = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False

    text = clean_text_and_normalize(html)

    # بررسی شباهت کلمات موجود در متن با لیست آژانس‌ها
    words = text.split()

    for airline in airlines:
        airline_normalized = airline.translate(PERSIAN_ARABIC_DIGITS).strip()
        if not airline_normalized:
            continue

        # بررسی تطابق مستقیم یا شباهت نزدیک (Fuzzy Match)
        if airline_normalized in text:
            return True

        # بررسی کلمه به کلمه برای نام‌های چندبخشی
        for word in words:
            # بررسی نسبت شباهت بین دو رشته (تطابق بالای ۸۰ درصد)
            ratio = difflib.SequenceMatcher(None, word, airline_normalized).ratio()
            if ratio >= 0.8:
                return True

    return False


def hot_validate_html(html: str):
    html_len = len(html)
    length_valid = MIN_HTML_LENGTH <= html_len <= MAX_HTML_LENGTH

    price = price_validation(html)
    if not price:
        return {"full": False, "length": length_valid, "agency": False}

    time = time_validation(html)
    if not time:
        return {"full": False, "length": length_valid, "agency": False}

    agency = agency_validation(html)

    return {"full": True, "length": length_valid, "agency": agency}
