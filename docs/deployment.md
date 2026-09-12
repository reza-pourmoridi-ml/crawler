# استقرار Docker

این استقرار شامل یک نمونه از هر پردازش است: `control`، `orchestrator`،
`scraper`، `learn` و `extractor`. PostgreSQL و Ollama نیز سرویس مستقل دارند.
همهٔ سرویس‌ها healthcheck، restart policy، محدودیت CPU/RAM/PID و لاگ چرخشی دارند.

## نکتهٔ مهم دربارهٔ مدل

ساخت image و اجرای عادی `docker compose up` هیچ مدلی را pull نمی‌کند. سرویس
`model-pull` پشت profile دستی `model-tools` است و فقط با دستور صریح اجرا می‌شود.
فایل local مدل `qwen2.5-coder:3b` و فایل production مدل
`qwen2.5-coder:14b` را مشخص می‌کند. volume مدل Ollama پایدار است؛ برای حفظ آن
از `docker compose down -v` استفاده نکنید.

## تست Ollama روی میزبان، پیش از Docker

ترمینال اول:

```bash
set -a
source deploy/ollama/local.env
set +a
OLLAMA_HOST="$OLLAMA_BIND_HOST" ollama serve
```

ترمینال دوم:

```bash
set -a
source deploy/ollama/local.env
set +a
ollama pull "$OLLAMA_MODEL"
ollama list
```

چون `OLLAMA_MODEL` در این فایل دقیقاً `qwen2.5-coder:3b` است، دستور بالا 14B
را دریافت نمی‌کند. برای اجرای مستقیم worker روی میزبان نیز همین فایل را source
کنید تا برنامه از `http://127.0.0.1:11434` استفاده کند.

## اجرای local با Docker

از ریشهٔ repository:

```bash
cp .env.docker.example .env.docker
```

رمز PostgreSQL را در هر دو متغیر `POSTGRES_PASSWORD` و `DATABASE_URL` یکسان
کنید. اگر رمز دارای نویسه‌های رزروشدهٔ URL است، آن را در `DATABASE_URL`
percent-encode کنید. سپس:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml config --quiet
DOCKER_BUILDKIT=1 docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml build
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml up -d postgres ollama
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml --profile model-tools run --rm model-pull
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml up -d
```

در صورت نیاز به داده‌های اولیه، فقط یک بار اجرا کنید:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml --profile setup run --rm seed
```

پنل روی `http://127.0.0.1:8000/control/dashboard` است. پورت Ollama در override
محلی فقط روی loopback منتشر می‌شود.

### استفاده از Ollama و مدل‌های از قبل موجود روی این لپ‌تاپ

روی این سیستم image قبلی Ollama و volume خارجی `crawler_ollama_data` موجود است.
برای جلوگیری از دانلود مجدد image و حفظ مدل‌های قبلی، فایل زیر را نیز به همهٔ
دستورهای local اضافه کنید:

```text
-f compose.ollama-existing.yaml
```

مثلاً:

```bash
docker stop ollama

docker compose --env-file .env.docker \
  -f compose.yaml \
  -f compose.local.yaml \
  -f compose.ollama-existing.yaml \
  up -d postgres ollama
```

توقف کانتینر قدیمی volume آن را حذف نمی‌کند. مدل‌های موجود فعلی
`qwen2.5-coder:7b` و `llama3.2:3b` هستند. مدل مورد انتظار تنظیم local یعنی
`qwen2.5-coder:3b` هنوز در آن volume وجود ندارد. بنابراین سه انتخاب دارید:

- تنظیم پیش‌فرض را نگه دارید و فقط `qwen2.5-coder:3b` را یک‌بار با profile
  `model-tools` pull کنید؛ فایل‌های قبلی حفظ می‌شوند.
- برای تست بدون هیچ دانلودی، در `.env.docker` موقتاً
  `OLLAMA_MODEL=llama3.2:3b` بگذارید؛ کیفیت coder آن پایین‌تر است.
- از `qwen2.5-coder:7b` موجود استفاده کنید؛ روی CPU این لپ‌تاپ کندتر است و
  به حافظهٔ بیشتری نیاز دارد.

## cache ساخت

فایل‌های dependency پیش از کد کپی می‌شوند و pip، npm و apt از BuildKit cache
mount استفاده می‌کنند. در نتیجه پس از تغییر فایل‌های Python/HTML، لایه‌های
dependency دوباره دانلود نمی‌شوند. فقط تغییر `requirements/*`، `package.json`،
`package-lock.json` یا بخش dependency در Dockerfile موجب بازسازی همان لایه است.

برای حفظ cache از `--no-cache` و `docker builder prune` استفاده نکنید. image
اسکرپر بر پایهٔ image رسمی Playwright است و مرورگر داخل همان base image قرار
دارد؛ در build دستور جداگانهٔ `playwright install` اجرا نمی‌شود.

## مشاهدهٔ وضعیت و لاگ crash

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml ps
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml logs -f --tail 200
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml logs --since 1h scraper learn extractor orchestrator
```

لاگ‌ها JSON هستند، exception را نگه می‌دارند و الگوهای رایج password، token،
cookie، JWT، ایمیل و شمارهٔ موبایل را redact می‌کنند. payload کامل سرچ، URL کامل
صفحه، HTML و پاسخ خام مدل لاگ نمی‌شوند. driver محلی Docker لاگ‌ها را با سقف
`5 × 10MB` برای هر کانتینر نگه می‌دارد و در crash/restart قابل مشاهده‌اند.

## رفتن روی 14B در سرور اصلی

فایل production را جدا بسازید؛ آن را روی سیستم local جایگزین `.env.docker`
نکنید:

```bash
cp .env.production.example .env.production
```

رمزها، مسیر فایل auth و منابع server را بررسی کنید. override فعلی برای ماشینی
با حداقل حدود 32GB RAM طراحی شده و تا 20GB RAM به Ollama می‌دهد. برای NVIDIA،
NVIDIA Container Toolkit را نصب و فایل GPU را نیز به همهٔ دستورها اضافه کنید.

CPU-only:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml build --parallel
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up -d postgres ollama
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml --profile model-tools run --rm model-pull
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up -d
```

NVIDIA GPU:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml up -d postgres ollama
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml --profile model-tools run --rm model-pull
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml up -d
```

قبل از pull می‌توانید موجودی volume را ببینید:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml exec ollama ollama list
```

تنها تفاوت مدل برای برنامه مقدار `OLLAMA_MODEL` است. ابتدا Ollama و مدل را آماده
کنید و بعد `learn` را بالا بیاورید. هر ماژول عمداً یک replica دارد؛ برای حفظ
رفتار و بودجهٔ منابع، با `--scale` تعداد workerها را زیاد نکنید.

## عملیات production

- کنترل‌پنل فقط روی `127.0.0.1` bind شده است؛ در سرور آن را پشت reverse proxy
  و TLS منتشر کنید.
- migration به‌صورت one-shot پیش از سرویس‌ها اجرا می‌شود و failure آن مانع شروع
  برنامه می‌شود.
- برای توقف بدون حذف داده: `docker compose ... down`. گزینهٔ `-v` دیتابیس،
  artifactها و مدل‌های دانلودشده را حذف می‌کند.
- از volume دیتابیس و `crawler_storage` پشتیبان دوره‌ای بگیرید. برای PostgreSQL
  می‌توان از `pg_dump` داخل سرویس `postgres` استفاده کرد.
- فایل auth از میزبان bind می‌شود و داخل image قرار نمی‌گیرد. مقدار
  `AUTH_STATE_HOST_PATH` باید پیش از start به یک فایل موجود اشاره کند.
