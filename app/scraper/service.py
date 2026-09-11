import asyncio
import random
import re
import shutil
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
HARD_PAUSE_LOAD_TIME = 20

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
    """
    اطمینان از اینکه صفحه از نظر شبکه و تغییرات DOM به پایداری نسبی رسیده است.
    مانع از ثبت اسکرین‌شات از Skeletonها یا وضعیت Loading می‌شود.
    """
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
    selectors = [
        "[class*='card']",
        "[class*='Card']",
        "[class*='flight']",
        "[class*='Flight']",
        "article",
        "button",
        "a",
    ]
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
                await move_mouse_naturally(
                    page,
                    target_x,
                    target_y,
                    steps=random.randint(10, 18),
                )
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


async def wait_for_manual_resolution_if_needed(
    page,
    headless: bool,
    timeout_sec: int = 120,
) -> str:
    matched = await detect_block_or_captcha(page)
    if not matched:
        return "clean"

    print(f"\n[!] Possible CAPTCHA / block detected. Matched: {matched}")
    if headless:
        print("[!] Headless mode is active. Cannot wait for manual input.")
        return "captcha_detected"

    print(
        f"[!] Headless is disabled. You have {timeout_sec} seconds "
        "to resolve it in the UI..."
    )
    start_time = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - start_time < timeout_sec:
        await asyncio.sleep(5)
        still_blocked = await detect_block_or_captcha(page)
        if not still_blocked:
            print("[+] CAPTCHA seems resolved! Continuing...")
            return "resolved"

    print("[!] Timeout waiting for manual CAPTCHA resolution.")
    return "captcha_timeout"


async def extract_visible_cards(page):
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
                            candidates.append(
                                {
                                    "selector": selector,
                                    "index": i,
                                    "text": normalized[:4000],
                                }
                            )
                except Exception:
                    pass
        except Exception:
            pass

    return candidates


async def extract_visible_texts_with_ids(page) -> list[dict]:
    """
    فقط متن‌های قابل مشاهده‌ی صفحه را استخراج می‌کند
    و به‌صورت یک لیست تخت با شناسه‌ی شمارشی برمی‌گرداند.
    """

    return await page.evaluate(
        """
        () => {
            const normalizeText = (value) =>
                String(value || "")
                    .replace(/\\u200c/g, " ")
                    .replace(/\\s+/g, " ")
                    .trim();

            const isVisible = (element) => {
                if (!element || !(element instanceof Element)) {
                    return false;
                }

                const style = window.getComputedStyle(element);

                if (
                    style.display === "none" ||
                    style.visibility === "hidden" ||
                    style.visibility === "collapse" ||
                    Number(style.opacity) === 0
                ) {
                    return false;
                }

                if (element.hasAttribute("hidden")) {
                    return false;
                }

                if (element.getAttribute("aria-hidden") === "true") {
                    return false;
                }

                const rect = element.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const ignoredTags = new Set([
                "SCRIPT",
                "STYLE",
                "NOSCRIPT",
                "TEMPLATE",
                "SVG",
                "PATH",
                "META",
                "LINK",
                "HEAD",
                "TITLE"
            ]);

            const elements = document.body
                ? Array.from(document.body.querySelectorAll("*"))
                : [];

            const results = [];
            const seen = new Set();
            let counter = 1;

            for (const element of elements) {
                if (
                    !isVisible(element) ||
                    !element.tagName ||
                    ignoredTags.has(element.tagName)
                ) {
                    continue;
                }

                const directTextParts = Array.from(element.childNodes)
                    .filter((node) => node.nodeType === Node.TEXT_NODE)
                    .map((node) => normalizeText(node.textContent))
                    .filter(Boolean);

                if (directTextParts.length === 0) {
                    continue;
                }

                const text = normalizeText(directTextParts.join(" "));
                if (!text) {
                    continue;
                }

                if (seen.has(text)) {
                    continue;
                }
                seen.add(text);

                const id = `text_${String(counter).padStart(6, "0")}`;
                counter += 1;

                results.push({
                    id,
                    text
                });
            }

            return results;
        }
        """
    )

async def extract_clean_html(page) -> str:
    return await page.evaluate(
        """
        () => {
            /*
             * Conservative semantic cleanup:
             *
             * - فقط عناصر موجود در REMOVE_ELEMENTS حذف می‌شوند.
             * - هیچ تگ دیگری حذف، unwrap یا جابه‌جا نمی‌شود.
             * - هیچ attributeای حذف نمی‌شود.
             * - هیچ عنصر خالی حذف نمی‌شود.
             * - commentها حفظ می‌شوند.
             * - متن و whitespace بدون تغییر حفظ می‌شوند.
             */

            const REMOVE_ELEMENTS = new Set([
                // CSS و JavaScript
                "style",
                "script",
                "link",

                // Metadata مربوط به head
                "head",
                "meta",
                "base",

                // گرافیک غیرمتنی
                "svg",
                "canvas",

                // محتوای رسانه‌ای غیرمتنی
                "video",
                "audio",

                // محتوای خارجی یا embed شده
                "iframe",
                "object",
                "embed"
            ]);

            const clone = document.documentElement.cloneNode(true);

            /*
             * حذف فقط تگ‌های صریحاً تعیین‌شده.
             *
             * querySelectorAll روی clone انجام می‌شود تا هیچ بخشی
             * از document اصلی تغییر نکند.
             */
            for (const tagName of REMOVE_ELEMENTS) {
                const elements = clone.querySelectorAll(tagName);

                for (const element of elements) {
                    element.remove();
                }
            }

            /*
             * عمداً انجام نمی‌دهیم:
             *
             * - حذف head
             * - حذف noscript یا template
             * - حذف comment
             * - حذف attributeها
             * - حذف class/id/role/aria/data
             * - حذف style attribute
             * - حذف whitespace
             * - حذف عناصر خالی
             * - unwrap کردن تگ‌های ناشناخته
             * - محدود کردن تگ‌ها به allowlist
             *
             * چون هرکدام ممکن است برای تشخیص ساختار، layout، لوگو،
             * CTA، route، قیمت یا duplicateهای responsive به LLM کمک کنند.
             */

            const doctype = document.doctype
                ? "<!DOCTYPE " + document.doctype.name + ">\\\\n"
                : "";

            return doctype + clone.outerHTML;
        }
        """
    )



async def extract_visible_semantic_text(page) -> dict:
    """
    فقط متن‌هایی را استخراج می‌کند که واقعاً برای کاربر قابل مشاهده‌اند.

    خروجی بر اساس نقش معنایی دسته‌بندی می‌شود:
    - headings
    - navigation
    - lists
    - cards
    - prices
    - buttons
    - links
    - form_fields
    - alerts
    - other_text
    """

    raw_data = await page.evaluate(
        """
        () => {
            const normalizeText = (value) => {
                return String(value || "")
                    .replace(/\\u200c/g, " ")
                    .replace(/\\s+/g, " ")
                    .trim();
            };

            const isVisible = (element) => {
                if (!element || !(element instanceof Element)) {
                    return false;
                }

                const style = window.getComputedStyle(element);

                if (
                    style.display === "none" ||
                    style.visibility === "hidden" ||
                    style.visibility === "collapse" ||
                    Number(style.opacity) === 0
                ) {
                    return false;
                }

                if (element.hasAttribute("hidden")) {
                    return false;
                }

                if (element.getAttribute("aria-hidden") === "true") {
                    return false;
                }

                const rect = element.getBoundingClientRect();

                return (
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const getDirectText = (element) => {
                const parts = [];

                for (const node of element.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = normalizeText(node.textContent);

                        if (text) {
                            parts.push(text);
                        }
                    }
                }

                return normalizeText(parts.join(" "));
            };

            const getElementText = (element, maxLength = 2000) => {
                const text = normalizeText(
                    element.innerText ||
                    element.textContent ||
                    ""
                );

                return text.slice(0, maxLength);
            };

            const getAccessibleName = (element) => {
                return normalizeText(
                    element.getAttribute("aria-label") ||
                    element.getAttribute("title") ||
                    element.getAttribute("alt") ||
                    element.innerText ||
                    element.textContent ||
                    ""
                );
            };

            const getHref = (element) => {
                if (!element.href) {
                    return null;
                }

                try {
                    return new URL(
                        element.href,
                        window.location.href
                    ).href;
                } catch {
                    return element.href;
                }
            };

            const result = {
                title: normalizeText(document.title),
                headings: [],
                navigation: [],
                lists: [],
                cards: [],
                prices: [],
                buttons: [],
                links: [],
                form_fields: [],
                alerts: [],
                other_text: []
            };

            /*
             * عنوان‌ها
             */
            for (const element of document.querySelectorAll(
                "h1, h2, h3, h4, h5, h6, [role='heading']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = getElementText(element, 500);

                if (!text) {
                    continue;
                }

                let level = null;

                const headingMatch = element.tagName.match(/^H([1-6])$/);

                if (headingMatch) {
                    level = Number(headingMatch[1]);
                } else {
                    const ariaLevel = Number(
                        element.getAttribute("aria-level")
                    );

                    level = ariaLevel || null;
                }

                result.headings.push({
                    level,
                    text
                });
            }

            /*
             * منوها و بخش‌های ناوبری
             */
            for (const element of document.querySelectorAll(
                "nav, [role='navigation']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = getElementText(element, 2000);

                if (!text) {
                    continue;
                }

                result.navigation.push({
                    label: normalizeText(
                        element.getAttribute("aria-label")
                    ) || null,
                    text
                });
            }

            /*
             * لیست‌های واقعی HTML و لیست‌های ARIA
             */
            for (const list of document.querySelectorAll(
                "ul, ol, [role='list'], [role='listbox']"
            )) {
                if (!isVisible(list)) {
                    continue;
                }

                const itemSelector =
                    ":scope > li, " +
                    ":scope > [role='listitem'], " +
                    ":scope > [role='option']";

                const items = [];

                for (const item of list.querySelectorAll(itemSelector)) {
                    if (!isVisible(item)) {
                        continue;
                    }

                    const text = getElementText(item, 1500);

                    if (text) {
                        items.push(text);
                    }
                }

                if (items.length > 0) {
                    result.lists.push({
                        type:
                            list.tagName === "OL"
                                ? "ordered"
                                : list.getAttribute("role") || "unordered",
                        label: normalizeText(
                            list.getAttribute("aria-label")
                        ) || null,
                        items
                    });
                }
            }

            /*
             * کارت‌ها و آیتم‌های تکرارشونده.
             *
             * این selector عمداً سایت‌محور نیست و کلاس‌هایی مثل
             * card، result، flight، ticket و hotel را بررسی می‌کند.
             */
            const cardSelector = [
                "article",
                "[role='article']",
                "[data-testid*='card' i]",
                "[data-testid*='result' i]",
                "[data-testid*='flight' i]",
                "[class*='card' i]",
                "[class*='result-item' i]",
                "[class*='flight-item' i]",
                "[class*='flight-card' i]",
                "[class*='ticket-card' i]",
                "[class*='hotel-card' i]"
            ].join(",");

            for (const element of document.querySelectorAll(cardSelector)) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = getElementText(element, 3000);

                if (!text || text.length < 10) {
                    continue;
                }

                result.cards.push({
                    label: normalizeText(
                        element.getAttribute("aria-label")
                    ) || null,
                    text
                });
            }

            /*
             * دکمه‌ها
             */
            for (const element of document.querySelectorAll(
                "button, [role='button'], input[type='button'], " +
                "input[type='submit']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = normalizeText(
                    element.value ||
                    getAccessibleName(element)
                );

                if (!text) {
                    continue;
                }

                result.buttons.push({
                    text,
                    disabled:
                        element.disabled === true ||
                        element.getAttribute("aria-disabled") === "true"
                });
            }

            /*
             * لینک‌ها
             */
            for (const element of document.querySelectorAll(
                "a[href], [role='link']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = getAccessibleName(element);

                if (!text) {
                    continue;
                }

                result.links.push({
                    text,
                    href: getHref(element)
                });
            }

            /*
             * فیلدهای فرم
             */
            for (const element of document.querySelectorAll(
                "input, select, textarea, [role='textbox'], " +
                "[role='combobox'], [role='searchbox']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const id = element.id;
                let label = "";

                if (id) {
                    try {
                        const labelElement = document.querySelector(
                            `label[for="${CSS.escape(id)}"]`
                        );

                        if (labelElement) {
                            label = getElementText(labelElement, 300);
                        }
                    } catch {
                        // Ignore invalid selector errors.
                    }
                }

                label = normalizeText(
                    label ||
                    element.getAttribute("aria-label") ||
                    element.getAttribute("placeholder") ||
                    element.name ||
                    ""
                );

                let value = null;

                if (
                    element.tagName === "SELECT" &&
                    element.selectedOptions &&
                    element.selectedOptions.length > 0
                ) {
                    value = normalizeText(
                        element.selectedOptions[0].textContent
                    );
                } else if (
                    element.type !== "password" &&
                    element.type !== "hidden"
                ) {
                    value = normalizeText(element.value || "");
                }

                if (!label && !value) {
                    continue;
                }

                result.form_fields.push({
                    type:
                        element.getAttribute("role") ||
                        element.type ||
                        element.tagName.toLowerCase(),
                    label: label || null,
                    value: value || null
                });
            }

            /*
             * خطاها، هشدارها و وضعیت‌ها
             */
            for (const element of document.querySelectorAll(
                "[role='alert'], [role='status'], " +
                "[aria-live='assertive'], [aria-live='polite']"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                const text = getElementText(element, 1500);

                if (!text) {
                    continue;
                }

                result.alerts.push({
                    role: element.getAttribute("role") || "live-region",
                    text
                });
            }

            /*
             * متن‌های مستقیم که در دسته‌های بالا قرار نگرفته‌اند.
             *
             * فقط direct text گرفته می‌شود تا متن فرزندان چندین بار
             * تکرار نشود.
             */
            const semanticContainer = [
                "h1", "h2", "h3", "h4", "h5", "h6",
                "nav",
                "ul", "ol",
                "article",
                "button",
                "a",
                "input",
                "select",
                "textarea",
                "[role='heading']",
                "[role='navigation']",
                "[role='list']",
                "[role='listbox']",
                "[role='article']",
                "[role='button']",
                "[role='link']",
                "[role='alert']",
                "[role='status']"
            ].join(",");

            for (const element of document.querySelectorAll(
                "main p, main span, main div, " +
                "[role='main'] p, [role='main'] span, [role='main'] div, " +
                "body > p"
            )) {
                if (!isVisible(element)) {
                    continue;
                }

                if (element.closest(semanticContainer)) {
                    continue;
                }

                const text = getDirectText(element);

                if (
                    !text ||
                    text.length < 2 ||
                    text.length > 1000
                ) {
                    continue;
                }

                result.other_text.push(text);
            }

            return result;
        }
        """
    )

    return clean_semantic_data(raw_data)


async def scrape_url(
    target_url: str,
    output_dir: Path,
    headless_mode: bool = True,
) -> dict:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    network_responses = []
    network_requests = []
    auth_state_file = Path("auth/auth.json")
    # executable_path = find_chromium_executable()
    # print(f"[*] Using Chromium executable: {executable_path}")
    has_auth_file = auth_state_file.exists()

    async with async_playwright() as p:
        context_args = {
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
        if has_auth_file and "alibaba.ir" in target_url:
            context_args["storage_state"] = str(auth_state_file)

        browser = await p.chromium.launch(
            # executable_path=executable_path,
            headless=headless_mode,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(**context_args)
        await context.add_init_script(
            "Object.defineProperty("
            "navigator, 'webdriver', {get: () => undefined}"
            ");"
        )
        page = await context.new_page()

        async def log_request(request):
            try:
                network_requests.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "resource_type": request.resource_type,
                    }
                )
            except Exception:
                pass

        async def capture_network(response):
            try:
                url = response.url
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type or any(
                    x in url.lower()
                    for x in ["api", "flight", "graphql"]
                ):
                    body = await response.text()
                    network_responses.append(
                        {
                            "url": url,
                            "status": response.status,
                            "data_preview": body[:10000],
                        }
                    )
            except Exception:
                pass

        page.on(
            "request",
            lambda req: asyncio.create_task(log_request(req)),
        )
        page.on(
            "response",
            lambda res: asyncio.create_task(capture_network(res)),
        )

        if "alibaba.ir" in target_url:
            try:
                await page.goto(
                    "https://www.alibaba.ir",
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                await human_pause(page, 1000, 2000)
            except Exception:
                pass

        print(f"[*] Navigating to: {target_url}")
        try:
            await page.goto(
                target_url,
                wait_until="domcontentloaded",
                timeout=50000,
            )
        except PlaywrightTimeoutError:
            print("[!] Timeout on initial load.")

        await wait_for_page_stability(page)
        await asyncio.sleep(HARD_PAUSE_LOAD_TIME)
        captcha_status = await wait_for_manual_resolution_if_needed(
            page,
            headless_mode,
        )
        if captcha_status in [
            "captcha_detected",
            "captcha_timeout",
        ]:
            screenshot_path = (
                    output_dir / "captcha.png"
            )
            await page.screenshot(
                path=str(screenshot_path),
                full_page=True,
            )
            await browser.close()
            return {
                "status": captcha_status,
                "screenshot": str(screenshot_path),
            }

        await human_like_scroll(page, max_steps=8)
        await wait_for_page_stability(
            page,
            stability_window_ms=3000,
        )

        current_url = page.url

        clean_html = await extract_clean_html(page)
        dom_path = output_dir / "page.html"
        dom_path.write_text(
            clean_html,
            encoding="utf-8",
        )

        screenshot_path = (
                output_dir / "screenshot.png"
        )
        await page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        extracted_texts = await extract_visible_texts_with_ids(page)
        texts_path = (
                output_dir / "texts.txt"
        )
        texts_path.write_text(
            "\\n".join(
                f"{item['id']}\\t{item['text']}"
                for item in extracted_texts
            ),
            encoding="utf-8",
        )


        if "alibaba.ir" in target_url and has_auth_file:
            try:
                await context.storage_state(
                    path=str(auth_state_file)
                )
            except Exception:
                pass

        await browser.close()
        return {
            "status": "success",
            "url": current_url,
            "dom_path": str(dom_path),
            "screenshot_path": str(screenshot_path),
            "texts_path": str(texts_path),
        }
