# Runtime storage

تمام artifactهای زنجیرهٔ پردازش در این پوشه قرار می‌گیرند:

```text
raw/         خروجی HTML، screenshot و متن scrape
learned/     قالب‌های یادگرفته‌شده برای هر وب‌سایت و نوع مسیر
extracted/   خروجی استخراج هر snapshot
temp/        فایل‌های موقت jobها؛ قابل پاک‌سازی خودکار
auth/        محل mount فایل وضعیت ورود داخل کانتینر
```

محتوای runtime این مسیر توسط `.gitignore` نادیده گرفته می‌شود و وارد repository
نخواهد شد. فقط این راهنما و فایل‌های `.gitkeep` ثبت می‌شوند.
