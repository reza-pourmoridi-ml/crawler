import asyncio
import json
import random
import re
import shutil
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

HARD_PAUSE_LOAD_TIME = 20
OUTPUT_DIR = Path("alibaba_raw_data")
OUTPUT_DIR.mkdir(exist_ok=True)


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


def random_delay_ms(min_ms=250, max_ms=900):
    return random.randint(min_ms, max_ms)


async def human_pause(page, min_ms=250, max_ms=900):
    await page.wait_for_timeout(random_delay_ms(min_ms, max_ms))


async def wait_for_page_stability(page, timeout_ms=15000, stability_window_ms=2000):
    print("[*] Waiting for page stability (DOM & Network)...")
    start_time = asyncio.get_running_loop().time()
    last_dom_size = 0
    stable_since = start_time

    while (asyncio.get_running_loop().time() - start_time) * 1000 < timeout_ms:
        current_dom_size = await page.evaluate("document.querySelectorAll('*').length")

        if current_dom_size != last_dom_size:
            stable_since = asyncio.get_running_loop().time()
            last_dom_size = current_dom_size

        elapsed_stable = (asyncio.get_running_loop().time() - stable_since) * 1000
        if elapsed_stable >= stability_window_ms:
            print(f"[+] Page stable for {stability_window_ms}ms.")
            break

        await asyncio.sleep(0.5)


async def move_mouse_naturally(page, x2, y2, steps=None):
    viewport = page.viewport_size or {"width": 1440, "height": 900}
    x1 = random.randint(50, max(60, viewport["width"] - 50))
    y1 = random.randint(50, max(60, viewport["height"] - 50))

    if steps is None:
        steps = random.randint(12, 24)

    await page.mouse.move(x1, y1)
    await human_pause(page, 80, 180)
    await page.mouse.move(x2, y2, steps=steps)


async def hover_visible_elements(page, max_hovers=3):
    selectors = ["[class*='card']", "[class*='Card']", "[class*='flight']", "[class*='Flight']", "article", "button", "a"]
    hovered = 0
    for selector in selectors:
        if hovered >= max_hovers:
            break
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue

        sample_size = min(count, 8)
        if sample_size <= 0:
            continue
        indices = list(range(sample_size))
        random.shuffle(indices)

        for idx in indices:
            if hovered >= max_hovers:
                break
            item = locator.nth(idx)
            try:
                await item.scroll_into_view_if_needed(timeout=1500)
                box = await item.bounding_box()
                if not box or box["width"] < 40 or box["height"] < 20:
                    continue
                target_x = int(box["x"] + min(box["width"] * 0.5, box["width"] - 5))
                target_y = int(box["y"] + min(box["height"] * 0.5, box["height"] - 5))
                await move_mouse_naturally(page, target_x, target_y, steps=random.randint(10, 18))
                await item.hover(timeout=1200)
                await human_pause(page, 180, 650)
                hovered += 1
            except Exception:
                continue


async def human_like_scroll(page, max_steps=10):
    print("[*] Starting adaptive scroll to trigger lazy loading...")
    stable_rounds = 0
    previous_height = await page.evaluate("() => document.body.scrollHeight")

    for _ in range(max_steps):
        distance = random.randint(700, 1500)
        await page.mouse.wheel(0, distance)
        if random.random() < 0.35:
            await human_pause(page, 250, 600)
            await page.mouse.wheel(0, -random.randint(80, 260))
        if random.random() < 0.45:
            await hover_visible_elements(page, max_hovers=random.randint(1, 2))
        await human_pause(page, 500, 1100)

        current_height = await page.evaluate("() => document.body.scrollHeight")
        viewport_height = await page.evaluate("() => window.innerHeight")
        scroll_y = await page.evaluate("() => window.scrollY")
        near_bottom = scroll_y + viewport_height >= current_height - 250

        if current_height <= previous_height + 80:
            stable_rounds += 1
        else:
            stable_rounds = 0

        previous_height = current_height

        if near_bottom and stable_rounds >= 2:
            break
        if stable_rounds >= 3:
            break


async def detect_block_or_captcha(page):
    try:
        title = (await page.title() or "").lower()
    except Exception:
        title = ""

    try:
        body_text = (await page.locator("body").inner_text(timeout=3000) or "").lower()
    except Exception:
        body_text = ""

    combined = f"{title}\n{body_text}"
    indicators = ["captcha", "i'm not a robot", "robot", "are you human", "access denied", "forbidden", "unusual traffic", "cloudflare", "verify you are human", "security check", "blocked", "کپچا", "ربات نیستم", "دسترسی غیرمجاز", "بررسی امنیتی"]
    matched = [x for x in indicators if x in combined]
    return matched


async def wait_for_manual_resolution_if_needed(page, headless: bool, timeout_sec: int = 120) -> str:
    matched = await detect_block_or_captcha(page)
    if not matched:
        return "clean"

    print(f"\n[!] Possible CAPTCHA / block detected. Matched: {matched}")
    if headless:
        print("[!] Headless mode is active. Cannot wait for manual input.")
        return "captcha_detected"

    print(f"[!] Headless is disabled. You have {timeout_sec} seconds to resolve it in the UI...")
    start_time = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - start_time < timeout_sec:
        await asyncio.sleep(5)
        still_blocked = await detect_block_or_captcha(page)
        if not still_blocked:
            print("[+] CAPTCHA seems resolved! Continuing...")
            return "resolved"

    print("[!] Timeout waiting for manual CAPTCHA resolution.")
    return "captcha_timeout"

# --- NEW OPTIMIZED EXTRACTION METHODS ---

async def extract_semantic_grouped_texts(page) -> dict:
    """Option 1: Component-Grouped JSON (Recommended)"""
    return await page.evaluate("""
        () => {
            function normalizeText(value) { return (value || "").replace(/\\s+/g, " ").trim(); }
            function getContainerSignature(element) {
                let current = element.parentElement;
                while (current && current !== document.body) {
                    const classes = Array.from(current.classList).join(" ").toLowerCase();
                    const tagName = current.tagName.toLowerCase();
                    if (tagName === "article" || tagName === "section" || tagName === "li" || tagName === "header" || classes.includes("card") || classes.includes("flight")) {
                        const classPart = current.className ? `.${Array.from(current.classList)[0]}` : "";
                        return `${tagName}${classPart}`;
                    }
                    current = current.parentElement;
                }
                return "global_content";
            }
            const grouped = {};
            const elements = document.body ? document.body.querySelectorAll("*") : [];
            for (const el of elements) {
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden" || ["SCRIPT","STYLE","SVG","PATH"].includes(el.tagName)) continue;
                const directText = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => normalizeText(n.textContent)).filter(Boolean).join(" ");
                if (!directText) continue;
                const sig = getContainerSignature(el);
                if (!grouped[sig]) grouped[sig] = [];
                grouped[sig].push(directText);
            }
            for (const k in grouped) grouped[k] = Array.from(new Set(grouped[k]));
            return grouped;
        }
    """)

async def extract_indented_text(page) -> str:
    """Option 2: Indented Semantic Text (Best for LLM Context)"""
    data = await extract_semantic_grouped_texts(page)
    lines = []
    for container, texts in data.items():
        lines.append(f"[{container.upper()}]")
        for t in texts:
            lines.append(f"  - {t}")
    return "\n".join(lines)

async def extract_schema_preserving_json(page) -> dict:
    """Option 3: Compressed CSS-mapped JSON"""
    return await page.evaluate("""
        () => {
            const result = {};
            const elements = document.body.querySelectorAll("*");
            for (const el of elements) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || ["SCRIPT","STYLE"].includes(el.tagName)) continue;
                const text = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).filter(Boolean).join(" ");
                if (text) {
                    let path = el.tagName.toLowerCase();
                    if (el.className) path += "." + Array.from(el.classList)[0];
                    if (!result[path]) result[path] = [];
                    result[path].push(text);
                }
            }
            return result;
        }
    """)

# --- ORIGINAL METHODS (PRESERVED) ---

async def extract_texts_grouped_by_dom_address(page) -> dict:
    return await page.evaluate(
        """
        () => {
            function normalizeText(value) {
                return (value || "").replace(/\\s+/g, " ").trim();
            }

            function escapeCssIdentifier(value) {
                if (window.CSS && typeof window.CSS.escape === "function") {
                    return CSS.escape(value);
                }
                return String(value).replace(/([^a-zA-Z0-9_-])/g, "\\\\$1");
            }

            function getElementClasses(element) {
                if (!element || !element.classList) {
                    return [];
                }
                return Array.from(element.classList).map((className) => className.trim()).filter(Boolean).sort();
            }

            function getDomAddress(element) {
                if (!element || element.nodeType !== Node.ELEMENT_NODE) {
                    return null;
                }
                const parts = [];
                let current = element;
                while (current && current.nodeType === Node.ELEMENT_NODE) {
                    const tagName = current.tagName.toLowerCase();
                    if (current.id) {
                        parts.unshift(`${tagName}#${escapeCssIdentifier(current.id)}`);
                        break;
                    }
                    let addressPart = tagName;
                    const parent = current.parentElement;
                    if (parent) {
                        const sameTagSiblings = Array.from(parent.children).filter((sibling) => sibling.tagName === current.tagName);
                        if (sameTagSiblings.length > 1) {
                            const index = sameTagSiblings.indexOf(current) + 1;
                            addressPart += `:nth-of-type(${index})`;
                        }
                    }
                    parts.unshift(addressPart);
                    current = parent;
                }
                return parts.join(" > ");
            }

            function stableHash(value) {
                let hash1 = 0xdeadbeef ^ value.length;
                let hash2 = 0x41c6ce57 ^ value.length;
                for (let i = 0; i < value.length; i++) {
                    const charCode = value.charCodeAt(i);
                    hash1 = Math.imul(hash1 ^ charCode, 2654435761);
                    hash2 = Math.imul(hash2 ^ charCode, 1597334677);
                }
                hash1 = Math.imul(hash1 ^ (hash1 >>> 16), 2246822507) ^ Math.imul(hash2 ^ (hash2 >>> 13), 3266489909);
                hash2 = Math.imul(hash2 ^ (hash2 >>> 16), 2246822507) ^ Math.imul(hash1 ^ (hash1 >>> 13), 3266489909);
                return `${(hash2 >>> 0).toString(16).padStart(8, "0")}${(hash1 >>> 0).toString(16).padStart(8, "0")}`;
            }

            function isIgnoredElement(element) {
                const ignoredTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "PATH", "META", "LINK", "HEAD", "TITLE"]);
                return ignoredTags.has(element.tagName);
            }

            function isElementVisible(element) {
                if (!element || !element.isConnected) return false;
                const style = window.getComputedStyle(element);
                return !(style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse" || Number(style.opacity) === 0) && element.getClientRects().length > 0;
            }

            const groupedTexts = {};
            const elements = document.body ? document.body.querySelectorAll("*") : [];
            for (const element of elements) {
                if (isIgnoredElement(element) || !isElementVisible(element)) continue;
                const directTextParts = Array.from(element.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => normalizeText(node.textContent)).filter(Boolean);
                if (directTextParts.length === 0) continue;
                const text = normalizeText(directTextParts.join(" "));
                if (!text) continue;
                const domAddress = getDomAddress(element);
                if (!domAddress) continue;
                const classes = getElementClasses(element);
                const classSignature = classes.length > 0 ? classes.join(".") : "__no_class__";
                const uniqueId = `text_${stableHash([classSignature, domAddress, text].join("|"))}`;
                if (!groupedTexts[domAddress]) groupedTexts[domAddress] = [];
                groupedTexts[domAddress].push({ id: uniqueId, tag: element.tagName.toLowerCase(), classes: classes, class_signature: classSignature, text: text });
            }
            return groupedTexts;
        }
        """
    )


async def extract_alibaba_data(target_url: str, headless_mode: bool = True) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_url = clean_filename(target_url.split("?")[0].split("//")[-1])
    file_prefix = f"{timestamp}_{sanitized_url}"
    auth_state_file = Path("auth/auth.json")
    has_auth_file = auth_state_file.exists()

    async with async_playwright() as p:
        context_args = {
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "viewport": {"width": 1440, "height": 900},
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "java_script_enabled": True,
            "bypass_csp": True,
            "ignore_https_errors": True,
        }
        if has_auth_file and "alibaba.ir" in target_url:
            context_args["storage_state"] = str(auth_state_file)

        browser = await p.chromium.launch(headless=headless_mode, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = await browser.new_context(**context_args)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await context.new_page()

        if "alibaba.ir" in target_url:
            try:
                await page.goto("https://www.alibaba.ir", wait_until="domcontentloaded", timeout=20000)
                await human_pause(page, 1000, 2000)
            except Exception: pass

        print(f"[*] Navigating to: {target_url}")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=50000)
        except PlaywrightTimeoutError: print("[!] Timeout on initial load.")

        await wait_for_page_stability(page)
        await asyncio.sleep(HARD_PAUSE_LOAD_TIME)

        captcha_status = await wait_for_manual_resolution_if_needed(page, headless_mode)
        if captcha_status in ["captcha_detected", "captcha_timeout"]:
            screenshot_path = OUTPUT_DIR / f"{file_prefix}_captcha.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            await browser.close()
            return {"status": captcha_status, "screenshot": str(screenshot_path)}

        await human_like_scroll(page, max_steps=8)
        await wait_for_page_stability(page, stability_window_ms=3000)

        # Execution of all extraction methods
        original_grouped = await extract_texts_grouped_by_dom_address(page)
        semantic_grouped = await extract_semantic_grouped_texts(page)
        indented_text = await extract_indented_text(page)
        schema_json = await extract_schema_preserving_json(page)

        # Saving outputs
        (OUTPUT_DIR / f"{file_prefix}_original_texts.json").write_text(json.dumps(original_grouped, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUT_DIR / f"{file_prefix}_semantic_grouped.json").write_text(json.dumps(semantic_grouped, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUT_DIR / f"{file_prefix}_llm_friendly.txt").write_text(indented_text, encoding="utf-8")
        (OUTPUT_DIR / f"{file_prefix}_compressed_schema.json").write_text(json.dumps(schema_json, ensure_ascii=False, indent=2), encoding="utf-8")

        screenshot_path = OUTPUT_DIR / f"{file_prefix}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)

        await browser.close()
        return {"status": "success", "url": page.url, "screenshot": str(screenshot_path)}

if __name__ == "__main__":
    test_url = "https://www.snapptrip.ir/flights/THR_city/MHD_city?adultCount=1&departureDate=2026-07-24"
    asyncio.run(extract_alibaba_data(test_url, headless_mode=True))
