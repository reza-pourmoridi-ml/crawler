import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright


AUTH_DIR = Path("auth")
AUTH_DIR.mkdir(parents=True, exist_ok=True)

AUTH_STATE_FILE = AUTH_DIR / "alibaba.json"
LOGIN_URL = "https://www.alibaba.ir/"
START_TIME = time.monotonic()


def log(message: str) -> None:
    elapsed = time.monotonic() - START_TIME
    print(f"[{elapsed:7.2f}s] {message}", flush=True)


async def save_auth():
    log("Starting Playwright")

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

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="fa-IR",
            timezone_id="Asia/Tehran",
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
        )

        log("Context created")

        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        )

        page = await context.new_page()
        log("Page created")

        log(f"Opening {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        log("Page loaded")

        print()
        print("[*] داخل مرورگر لاگین کن.")
        print("[*] اگر سایت شماره موبایل یا کد تایید خواست، دستی وارد کن.")
        print("[*] بعد از اینکه مطمئن شدی لاگین هستی، در همین ترمینال Enter بزن.")
        print()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, input)

        try:
            await context.storage_state(
                path=str(AUTH_STATE_FILE),
                indexed_db=True,
            )
        except TypeError:
            await context.storage_state(path=str(AUTH_STATE_FILE))

        print(f"[+] Auth state saved to: {AUTH_STATE_FILE.resolve()}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(save_auth())
