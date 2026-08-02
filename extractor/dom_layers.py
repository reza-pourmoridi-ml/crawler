from typing import List
from bs4 import BeautifulSoup, Tag


def extract_dom_layers(html: str) -> List[str]:
    """
    دقیقاً یک لایه به داخل قطعه HTML ورودی می‌رود و تمام فرزندان مستقیمی
    که خودشان والد هستند (حداقل یک تگ فرزند دارند) را همراه با تمام زیرمجموعه‌شان
    به عنوان رشته‌های HTML مجزا برمی‌گرداند.
    """
    if not isinstance(html, str):
        raise TypeError("html باید از نوع str باشد.")

    # استفاده از html.parser
    soup = BeautifulSoup(html, "html.parser")

    # برای اینکه دقیقاً روی سطح اول قطعه کد ورودی کار کنیم:
    # تمام تگ‌های سطح اول موجود در ریشه پارسر را می‌گیریم.
    # اگر ورودی یک تگ منفرد مثل <html>...</html> یا <div>...</div> باشد،
    # top_level_tags فقط شامل همان یک تگ خواهد بود.
    top_level_tags = [node for node in soup.contents if isinstance(node, Tag)]

    if not top_level_tags:
        return []

    parents_html = []

    # برای هر تگ در سطح اول، فرزندان مستقیمش را بررسی می‌کنیم (یک لایه نفوذ)
    for root_tag in top_level_tags:
        for child in root_tag.children:
            if isinstance(child, Tag):
                # بررسی اینکه آیا این فرزند خودش والد است (حداقل یک فرزند تگی دارد)
                has_child_tag = any(isinstance(c, Tag) for c in child.children)
                if has_child_tag:
                    parents_html.append(str(child))

    return parents_html
