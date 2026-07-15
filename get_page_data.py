import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# آدرس هدف تست
# TARGET_URL = "https://www.alibaba.ir/flights/THR-MHD?adult=1&child=0&infant=0&departing=1405-05-02"
TARGET_URL = "https://www.alibaba.ir/international/IKA-ISTALL?adult=1&child=0&infant=0&departing=1405-05-02&flightClass=economy"

# TARGET_URL = "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=mhd,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isDomestic=true&isAnyWhere=false"
# TARGET_URL = "https://www.flytoday.ir/flight/search?departure=thr,1&arrival=ist,1&departureDate=2026-07-24&adt=1&chd=0&inf=0&cabin=1&isAnyWhere=false"
#
# TARGET_URL = "https://www.snapptrip.ir/flights/THR_city/MHD_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali"
# TARGET_URL = "https://www.snapptrip.ir/inter-flights/THR_city/IST_city?adultCount=1&childCount=0&infantCount=0&departureDate=2026-07-24&source=searchBox&dateType=jalali&cabinType=ECONOMY"
#
# TARGET_URL = "https://mrbilit.com/flights/THR-MHD?departureDate=1405-05-02"
# TARGET_URL = "https://mrbilit.com/flights/IKA-ISTALL?departureDate=1405-05-02&cabinClass=/P"
#
# TARGET_URL = "https://ghasedak24.com/flights/THR-MHD?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0"
# TARGET_URL = "https://ghasedak24.com/flights/IKA-ISTALL?departure-date=1405-05-02&adult-count=1&child-count=0&infant-count=0&cabin=Y"
OUTPUT_DIR = Path("alibaba_raw_data")
OUTPUT_DIR.mkdir(exist_ok=True)
AUTH_STATE_FILE = Path("auth_state.json")


def clean_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name)


def find_chromium_executable():
    candidates = [
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    raise FileNotFoundError(
        "Chromium executable not found. Install it with apt and verify using `which chromium-browser` or `which chromium`."
    )


async def human_like_scroll(page, steps=15, scroll_delay=1200):
    """
    اسکرول شبیه‌سازی شده به رفتار انسان برای باز کردن کارت‌های Lazy Load
    """
    print("[*] Starting smart scroll to trigger lazy loading...")
    for step in range(steps):
        await page.mouse.wheel(0, 1500)
        await page.wait_for_timeout(scroll_delay)

        if step % 3 == 0:
            await page.mouse.wheel(0, -200)
            await page.wait_for_timeout(300)


async def detect_block_or_captcha(page):
    """
    تشخیص تقریبی بلاک/کپچا با تکیه بر title + متن body
    """
    try:
        title = (await page.title() or "").lower()
    except Exception:
        title = ""

    try:
        body_text = (await page.locator("body").inner_text(timeout=5000) or "").lower()
    except Exception:
        body_text = ""

    combined = f"{title}\n{body_text}"

    indicators = [
        "captcha",
        "i'm not a robot",
        "robot",
        "are you human",
        "access denied",
        "forbidden",
        "unusual traffic",
        "cloudflare",
        "verify you are human",
        "security check",
        "blocked",
        "کپچا",
        "ربات نیستم",
        "دسترسی غیرمجاز",
        "بررسی امنیتی",
    ]

    matched = [x for x in indicators if x in combined]
    return matched


async def wait_for_manual_resolution_if_needed(page):
    """
    اگر کپچا/بلاک تشخیص داده شد، به کاربر فرصت حل دستی می‌دهد.
    """
    matched = await detect_block_or_captcha(page)
    if not matched:
        return False

    print("\n[!] Possible CAPTCHA / block detected.")
    print(f"[!] Matched indicators: {matched}")
    print("[!] Please solve it manually in the opened browser window.")
    print("[!] After solving, press ENTER here to continue...")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, input)

    print("[*] Waiting a bit after manual intervention...")
    await page.wait_for_timeout(5000)
    return True


async def extract_visible_cards(page):
    """
    استخراج ساده‌ی کاندیدهای متنی از کارت‌ها/بخش‌های صفحه برای بررسی اولیه.
    این بخش generic است و بعداً می‌شود selectorهای دقیق‌تری برای علی‌بابا نوشت.
    """
    candidates = []

    selectors = [
        "article",
        "[class*='card']",
        "[class*='Card']",
        "[class*='flight']",
        "[class*='Flight']",
        "[data-testid]",
        "section",
    ]

    seen = set()

    for selector in selectors:
        try:
            locators = page.locator(selector)
            count = await locators.count()
            for i in range(min(count, 100)):
                try:
                    text = (await locators.nth(i).inner_text(timeout=2000)).strip()
                    if text and len(text) > 30:
                        normalized = re.sub(r"\s+", " ", text)
                        if normalized not in seen:
                            seen.add(normalized)
                            candidates.append({
                                "selector": selector,
                                "index": i,
                                "text": normalized[:4000]
                            })
                except Exception:
                    pass
        except Exception:
            pass

    return candidates


async def extract_alibaba_data():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_prefix = f"alibaba_thr_mhd_{timestamp}"

    network_responses = []
    network_requests = []

    AUTH_STATE_FILE = Path("auth/alibaba.json")
    HEADLESS_MODE = True

    executable_path = find_chromium_executable()
    print(f"[*] Using Chromium executable: {executable_path}")

    if not AUTH_STATE_FILE.exists():
        print(f"[!] Auth state file not found: {AUTH_STATE_FILE}")
        print("[!] First run save_auth.py locally, then copy auth/alibaba.json to the server.")
        return

    async with async_playwright() as p:
        context_args = {
            "storage_state": str(AUTH_STATE_FILE),
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1440, "height": 900},
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "java_script_enabled": True,
            "bypass_csp": True,
            "ignore_https_errors": True,
        }

        browser = await p.chromium.launch(
            executable_path=executable_path,
            headless=HEADLESS_MODE,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1440,900",
            ],
        )

        context = await browser.new_context(**context_args)

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page = await context.new_page()

        async def log_request(request):
            try:
                network_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "headers": await request.all_headers(),
                })
            except Exception:
                pass

        async def capture_network(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "")

                if (
                        "application/json" in content_type
                        or "api" in url.lower()
                        or "flight" in url.lower()
                        or "graphql" in url.lower()
                ):
                    body = await response.text()
                    network_responses.append({
                        "url": url,
                        "status": response.status,
                        "content_type": content_type,
                        "headers": response.headers,
                        "data_preview": body[:20000],
                    })
            except Exception:
                pass

        page.on("request", lambda req: asyncio.create_task(log_request(req)))
        page.on("response", lambda res: asyncio.create_task(capture_network(res)))

        print("[*] Navigating to Alibaba home first to establish cookies...")
        try:
            await page.goto(
                "https://www.alibaba.ir",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[!] Warning: Initial home navigation issue, continuing... Error: {e}")

        print(f"[*] Navigating to flight search page: {TARGET_URL}")
        try:
            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except PlaywrightTimeoutError:
            print("[!] Timeout on page load. Attempting to extract what is available.")

        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            print("[!] networkidle timeout; continuing with current DOM.")

        # بررسی اینکه سشن هنوز معتبر است یا نه.
        login_required = False

        try:
            login_required = bool(
                await page.query_selector("input[type='tel']")
                or await page.query_selector("text='ورود یا ثبت‌نام'")
                or await page.query_selector("text='ورود / ثبت‌نام'")
                or await page.query_selector("text='شماره موبایل'")
            )
        except Exception:
            login_required = False

        if login_required:
            print("[!] Authentication required or session expired.")
            print("[!] This server is running headless, so manual login is not possible here.")
            print("[!] Run save_auth.py again locally and upload the new auth/alibaba.json.")

            screenshot_path = OUTPUT_DIR / f"{file_prefix}_auth_required.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"[+] Auth-required screenshot saved to: {screenshot_path}")
            except Exception:
                pass

            await browser.close()
            return

        solved = await wait_for_manual_resolution_if_needed(page)
        if solved:
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

        await human_like_scroll(page, steps=12, scroll_delay=1200)
        await page.wait_for_timeout(4000)

        current_url = page.url
        page_title = await page.title()

        print(f"[*] Final URL: {current_url}")
        print(f"[*] Page title: {page_title}")

        dom_content = await page.content()
        dom_path = OUTPUT_DIR / f"{file_prefix}.html"
        dom_path.write_text(dom_content, encoding="utf-8")
        print(f"[+] Final DOM saved to: {dom_path}")

        body_text = await page.locator("body").inner_text()
        text_path = OUTPUT_DIR / f"{file_prefix}.txt"
        text_path.write_text(body_text, encoding="utf-8")
        print(f"[+] Page text saved to: {text_path}")

        screenshot_path = OUTPUT_DIR / f"{file_prefix}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"[+] Full-page screenshot saved to: {screenshot_path}")

        network_path = OUTPUT_DIR / f"{file_prefix}_network.json"
        network_path.write_text(
            json.dumps(network_responses, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[+] Captured network responses saved to: {network_path}")

        requests_path = OUTPUT_DIR / f"{file_prefix}_requests.json"
        requests_path.write_text(
            json.dumps(network_requests, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[+] Captured requests saved to: {requests_path}")

        card_candidates = await extract_visible_cards(page)
        cards_path = OUTPUT_DIR / f"{file_prefix}_cards.json"
        cards_path.write_text(
            json.dumps(card_candidates, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[+] Candidate card texts saved to: {cards_path}")

        meta = {
            "target_url": TARGET_URL,
            "final_url": current_url,
            "title": page_title,
            "timestamp": timestamp,
            "chromium_executable": executable_path,
            "auth_state_file": str(AUTH_STATE_FILE),
            "headless": HEADLESS_MODE,
        }

        meta_path = OUTPUT_DIR / f"{file_prefix}_meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[+] Meta info saved to: {meta_path}")

        # ذخیره مجدد سشن، چون ممکن است سایت Cookie یا Token را تمدید کرده باشد.
        try:
            await context.storage_state(path=str(AUTH_STATE_FILE))
            print(f"[+] Auth state refreshed: {AUTH_STATE_FILE}")
        except Exception as e:
            print(f"[!] Could not refresh auth state: {e}")

        await browser.close()
        print("[*] Browser closed. Step 1 extraction completed successfully.")


if __name__ == "__main__":
    asyncio.run(extract_alibaba_data())
