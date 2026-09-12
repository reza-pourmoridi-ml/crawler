import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright


AUTH_STATE_FILE = Path(__file__).resolve().parent / "auth.json"
AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
LOGIN_URL = "https://www.alibaba.ir/"

START_TIME = time.monotonic()


def log(message: str) -> None:
    elapsed = time.monotonic() - START_TIME
    print(f"[{elapsed:7.2f}s] {message}", flush=True)


async def save_auth() -> None:
    log("Starting Playwright")

    # بررسی می‌کنیم آیا وضعیت ورود قبلی وجود دارد یا نه.
    has_existing_auth = AUTH_STATE_FILE.is_file()

    async with async_playwright() as p:
        log("Launching Chromium")

        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--ozone-platform=x11",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--window-size=1440,900",
            ],
        )

        log("Chromium launched")

        context_options = {
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "viewport": {
                "width": 1440,
                "height": 900,
            },
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "java_script_enabled": True,
            "bypass_csp": True,
            "ignore_https_errors": True,
        }

        # اگر فایل قبلی موجود است، کوکی‌ها و Local Storage آن را
        # هنگام ساخت BrowserContext بارگذاری می‌کنیم.
        if has_existing_auth:
            context_options["storage_state"] = str(AUTH_STATE_FILE)
            log(f"Loading existing auth state: {AUTH_STATE_FILE}")
        else:
            log("No existing auth state found; starting with a clean context")

        context = await browser.new_context(**context_options)
        log("Context created")

        await context.add_init_script(
            """
            Object.defineProperty(navigator, "webdriver", {
                get: () => undefined
            });
            """
        )

        page = await context.new_page()
        log("Page created")

        try:
            log(f"Opening {LOGIN_URL}")

            await page.goto(
                LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            log("Page loaded")

            print()

            if has_existing_auth:
                print("[*] وضعیت ورود قبلی بارگذاری شد.")
                print("[*] وضعیت حساب را داخل مرورگر بررسی کن.")
                print("[*] اگر هنوز لاگین هستی، بدون انجام کار دیگری Enter بزن.")
                print("[*] اگر لاگین نیستی، دستی لاگین کن و سپس Enter بزن.")
            else:
                print("[*] وضعیت ورود قبلی پیدا نشد.")
                print("[*] داخل مرورگر به‌صورت دستی لاگین کن.")
                print("[*] اگر شماره موبایل یا کد تأیید خواست، دستی وارد کن.")
                print("[*] پس از اطمینان از ورود، در این ترمینال Enter بزن.")

            print()

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                input,
                "Press Enter to save the current authentication state... ",
            )

            log("Saving authentication state")

            try:
                # Playwrightهای جدید می‌توانند IndexedDB را نیز ذخیره کنند.
                await context.storage_state(
                    path=str(AUTH_STATE_FILE),
                    indexed_db=True,
                )
            except TypeError:
                # سازگاری با نسخه‌هایی که indexed_db را پشتیبانی نمی‌کنند.
                await context.storage_state(
                    path=str(AUTH_STATE_FILE),
                )

            log(f"Auth state saved to: {AUTH_STATE_FILE.resolve()}")

        finally:
            log("Closing browser")
            await browser.close()
            log("Browser closed")


if __name__ == "__main__":
    try:
        asyncio.run(save_auth())
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user.")
