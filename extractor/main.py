import os
from dom_layers import extract_dom_layers
from fast_validation import hot_validate_html
FILE_PATH = "alibaba_raw_data/20260801_110559_ghasedak24_com_flights_IKA-ISTALL.html"
if not os.path.exists(FILE_PATH):
    raise FileNotFoundError(f"فایل در مسیر مشخص شده یافت نشد: {FILE_PATH}")

with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

layers_1 = extract_dom_layers(html)
layers_2 = extract_dom_layers(layers_1[0])
print(hot_validate_html(layers_1[0]))
print(hot_validate_html(layers_2[0]))

