# Crawler Control

پنل فارسی مدیریت ایرلاین‌ها، وب‌سایت‌ها و کد فرودگاه‌ها، با FastAPI، SQLAlchemy و PostgreSQL.

## اجرا

دستورها را از ریشهٔ پروژه اجرا کنید. محیط مجازی فعلی در پوشهٔ بالاتر قرار دارد؛ تنظیم اتصال PostgreSQL از `DATABASE_URL` در `.env` خوانده می‌شود.

```bash
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m app.infra.seeders.run
../.venv/bin/python -m app.control
```

پنل: <http://127.0.0.1:8000/control/dashboard>

مستندات تعاملی API: <http://127.0.0.1:8000/docs>

برای انتخاب پورت یا فعال‌کردن بارگذاری مجدد هنگام توسعه:

```bash
../.venv/bin/python -m uvicorn app.control.main:app --host 127.0.0.1 --port 8000 --reload
```

## مدل‌ها

- `Airline`: نام رسمی فارسی و مجموعهٔ نام‌های مستعار؛ حذف ایرلاین نام‌های مستعارش را هم حذف می‌کند.
- `Website`: نام یکتا و نشانی اصلی یکتای وب‌سایت، مانند `https://www.alibaba.ir`.
- `FlightPath`: نگاشت **یک فرودگاه در یک وب‌سایت**، با `website_id`، `airport_name_fa` و `code`. این مدل یک جفت مبدأ/مقصد نیست. مثلاً مشهد در علی‌بابا با `MHD` ثبت می‌شود.

نام فرودگاه و کد آن در هر وب‌سایت یکتا هستند؛ همان نام یا کد می‌تواند در وب‌سایت دیگری ثبت شود. بزرگی/کوچکی حروف و نشانه‌های کد حفظ می‌شوند و مقدارهایی مثل `THR_city` و `thr,1` معتبرند. برای حذف وب‌سایت، ابتدا کدهای وابسته را حذف کنید یا به وب‌سایت دیگری منتقل کنید.

## صفحات و API

| بخش | فهرست وب | API |
| --- | --- | --- |
| ایرلاین‌ها | `/control/airlines/page` | `/control/airlines` |
| وب‌سایت‌ها | `/control/websites/page` | `/control/websites` |
| کد فرودگاه‌ها | `/control/flight-paths/page` | `/control/flight-paths` |

برای هر API، `GET` فهرست و `POST` ثبت رکورد جدید را انجام می‌دهد. روی `/{id}` نیز `GET`، `PUT` و `DELETE` برای جزئیات، ویرایش و حذف وجود دارند. ثبت موفق `201`، حذف موفق `204`، رکورد ناموجود `404`، تعارض `409` و ورودی نامعتبر `422` برمی‌گردانند.

صفحات هر بخش، ثبت در `/page/new`، مشاهده در `/page/{id}`، ویرایش در `/page/{id}/edit` و تأیید حذف در `/page/{id}/delete` دارند. حذف تنها با ارسال فرم `POST` انجام می‌شود. فهرست کد فرودگاه‌ها با `?website_id=1` قابل فیلتر است.

## دادهٔ نمونه

داده‌های آزمایشی وب‌سایت‌ها و کد فرودگاه‌ها را در این فایل‌ها تکمیل کنید:

- `app/infra/seeders/websites.py`
- `app/infra/seeders/flight_paths.py`

سیدر وب‌سایت‌ها باید پیش از سیدر کد فرودگاه‌ها اجرا شود؛ اجرای عمومی سیدرها این ترتیب را رعایت می‌کند. سیدرهای جدید فقط موارد موجودنبوده را اضافه می‌کنند و ویرایش‌های دستی را بازنویسی نمی‌کنند. نمونه‌ها صرفاً دادهٔ شروع کار هستند و تأیید صحت جاری URLهای وب‌سایت‌ها محسوب نمی‌شوند.

## تست

```bash
../.venv/bin/python -m unittest discover -s tests -v
```

تست‌های سرویس و صفحات از دیتابیس SQLite مجزا استفاده می‌کنند و داده‌های PostgreSQL اصلی را تغییر نمی‌دهند. Migrationها برای PostgreSQL نوشته شده‌اند.

## زنجیرهٔ scrape، learn و extractor

`orchestrator` تنها زمان‌بند زنجیره است. هر پنج دقیقه برای هر درخواست و وب‌سایت دارای تنظیمات کامل، job از نوع `scrape` می‌سازد؛ وجود job فعال برای همان درخواست/وب‌سایت مانع تکرار می‌شود. worker اسکرپر HTML را ذخیره می‌کند و صف وضعیت آن را به `done` تغییر می‌دهد. orchestrator در بررسی بعدی مراحل بعد را می‌سازد. هر worker فقط نوع job خودش را مصرف می‌کند؛ وضعیت‌های صف همان `pending`، `running`، `done` و `failed` هستند و retry و heartbeat از زیرساخت موجود استفاده می‌کنند.

ماژول `app.learn` توابع سلول‌های ۵ و ۷ نوت‌بوک `test-ollama.ipynb` را اجرا می‌کند: استخراج کاندیدها و سپس تأیید کارت‌ها با Ollama. prompt، تنظیمات مدل و منطق پیمایش نوت‌بوک حفظ شده‌اند. نصب ابزارها، اجرای batch دیتاست Kaggle و راه‌اندازی Ollama درون نوت‌بوک، جای خود را به تنظیمات سرویس و job داده‌اند. Ollama باید جداگانه اجرا شود و مدل از قبل در آن موجود باشد؛ worker مدل را دانلود یا سرور Ollama را اجرا نمی‌کند.

learn برای هر `(website_id, route_type)` مستقل است: داخلی و خارجی فایل‌های جدا دارند. پیش‌فرض نوسازی هفت روز است و با `LEARN_INTERVAL_SECONDS` تغییر می‌کند. ورودی، آخرین snapshot موفق همان وب‌سایت و نوع مسیر است؛ بنابراین شروع learn به وجود حداقل یک درخواست و crawl موفق وابسته است. برای هر داده learn مجزا اجرا نمی‌شود. تا وقتی job learn فعال است، نمونهٔ جدید job learn دیگری ایجاد نمی‌کند. پس از پایان retryهای صف، `LEARN_RETRY_SECONDS` حداقل فاصله از زمان برنامه‌ریزی آخرین تلاش ناموفق را تعیین می‌کند.

ماژول `app.extractor` سلول‌های ۹ و ۱۰ را اجرا می‌کند: تطبیق ساختار با آستانهٔ `0.95` و استخراج `time`، `price`، `airline` و `text`. قیمت و ساعت مطابق قواعد نوت‌بوک استخراج می‌شوند و تبدیل واحد یا نرمال‌سازی جدیدی اضافه نشده است. ایرلاین‌ها در هر job از دیتابیس به شکل `{نام رسمی: [نام‌ها و نام‌های مستعار]}` خوانده می‌شوند. این worker به Ollama و Node نیاز ندارد. اگر learn هنوز وجود نداشته باشد، استخراج در orchestrator منتظر می‌ماند؛ اگر نسخهٔ قبلی موجود باشد، هنگام نوسازی هم قابل استفاده است. فایل learn فقط پس از خروجی غیرخالی و به‌صورت atomic جایگزین می‌شود.

وابستگی‌های جدید را در محیط پروژه نصب کنید؛ Node و jsdom فقط برای worker learn لازم‌اند:

```bash
../.venv/bin/python -m pip install -r requirements-workers.txt
npm ci --ignore-scripts --no-audit --no-fund
ollama pull qwen2.5-coder:14b
```

Ollama را به‌صورت سرویس جدا اجرا کنید. سپس هر دستور زیر را در پردازش یا کانتینر مستقل اجرا کنید؛ یک نمونهٔ orchestrator کافی است:

```bash
../.venv/bin/python -m app.orchestration
../.venv/bin/python -m app.scraper
../.venv/bin/python -m app.learn
../.venv/bin/python -m app.extractor
```

workerهای learn و extractor هر job را در پردازش فرزند اجرا می‌کنند تا timeout واقعاً آن کار را متوقف کند. پیش‌فرض timeout به‌ترتیب شش ساعت و پنج دقیقه است. تعداد workerهای learn را متناسب با ظرفیت Ollama تعیین کنید؛ تعداد workerهای extractor مستقل است.

همهٔ پردازش‌ها باید به همان PostgreSQL و مسیر مشترک `STORAGE_ROOT` دسترسی داشته باشند. در اجرای چندماشینی/کانتینری، storage را در همان مسیر mount کنید و `OLLAMA_HOST` را برای worker learn تنظیم کنید. نام snapshot برای هر crawl یکتاست تا crawl بعدی ورودی learn را بازنویسی نکند:

```text
storage/raw/website_<id>/<domestic|international>/request_<id>/<snapshot_id>/page.html
storage/learned/website_<id>/<domestic|international>/tickets.json
storage/extracted/website_<id>/<domestic|international>/scrape_<job_id>.json
```

فایل learn همان لیست JSON از HTML کارت‌های تأییدشدهٔ نوت‌بوک است؛ در دیتابیس فقط metadata و وضعیت job نگهداری می‌شود. خروجی extractor نیز یک لیست JSON با چهار فیلد نوت‌بوک است. برای هر snapshot یک job استخراج ثبت می‌شود؛ شکست نهایی خودکار job تکراری ایجاد نمی‌کند. snapshotها و تاریخچهٔ jobها فعلاً نگهداری می‌شوند؛ پاک‌سازی خودکار تعریف نشده است. jobهای قدیمی `scrap` با payload بدون وب‌سایت به زنجیرهٔ جدید منتقل نمی‌شوند.
