import asyncio
import shutil
from pathlib import Path

from playwright.async_api import async_playwright


AUTH_DIR = Path("auth")
AUTH_DIR.mkdir(parents=True, exist_ok=True)

AUTH_STATE_FILE = AUTH_DIR / "alibaba.json"

LOGIN_URL = "https://www.alibaba.ir/"


def find_chromium_executable():
    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "msedge",
        "microsoft-edge",
    ]

    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    return None


async def save_auth():
    executable_path = find_chromium_executable()
    print(f"[*] Chromium executable: {executable_path or 'Playwright default'}")

    async with async_playwright() as p:
        launch_args = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1440,900",
            ],
        }

        if executable_path:
            launch_args["executable_path"] = executable_path

        browser = await p.chromium.launch(**launch_args)

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

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = await context.new_page()

        print(f"[*] Opening: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        print()
        print("[*] داخل مرورگر لاگین کن.")
        print("[*] اگر سایت شماره موبایل یا کد تایید خواست، دستی وارد کن.")
        print("[*] بعد از اینکه مطمئن شدی لاگین هستی، در همین ترمینال Enter بزن.")
        print()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, input)

        # ذخیره Cookie و LocalStorage.
        # اگر نسخه Playwright جدید باشد، IndexedDB هم ذخیره می‌شود.
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
