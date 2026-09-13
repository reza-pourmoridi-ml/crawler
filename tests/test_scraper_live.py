import json
import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from app.infra.config import settings


LIVE_URL = os.getenv("CRAWLER_LIVE_SCRAPE_URL")
if LIVE_URL:
    from playwright.async_api import async_playwright
    from app.scraper.service import capture_page_screenshot


@unittest.skipUnless(
    LIVE_URL,
    "Set CRAWLER_LIVE_SCRAPE_URL to run the live provider diagnostic",
)
class LiveScraperPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_page_reaches_flight_results(self):
        output_dir = Path(
            os.getenv(
                "CRAWLER_LIVE_OUTPUT_DIR",
                "/tmp/crawler-live-scrape",
            )
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        auth_state = Path(settings.auth_state_file)
        self.assertTrue(
            auth_state.is_file(),
            f"Auth state file does not exist: {auth_state}",
        )

        response_statuses = []
        failed_requests = []

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            self.addAsyncCleanup(browser.close)
            context = await browser.new_context(
                storage_state=str(auth_state),
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
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined});"
            )
            page = await context.new_page()

            def safe_url(url):
                parsed = urlsplit(url)
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"[:500]

            def record_response(response):
                if any(
                    marker in response.url.lower()
                    for marker in ("api", "flight", "graphql")
                ):
                    response_statuses.append(
                        {"status": response.status, "url": safe_url(response.url)}
                    )

            def record_failure(request):
                failed_requests.append(
                    {
                        "url": safe_url(request.url),
                        "failure": request.failure,
                    }
                )

            page.on("response", record_response)
            page.on("requestfailed", record_failure)

            await page.goto(
                LIVE_URL,
                wait_until="domcontentloaded",
                timeout=50_000,
            )

            try:
                await page.wait_for_function(
                    """
                    () => {
                        const text = document.body?.innerText || "";
                        const hasPrice = /[۰-۹0-9][۰-۹0-9,٬.]*\\s*(تومان|ریال)/.test(text);
                        const hasTicketAction = /(انتخاب|خرید)\\s*(بلیط|پرواز)?/.test(text);
                        const hasEmptyState = /(پروازی پیدا نشد|نتیجه‌ای یافت نشد)/.test(text);
                        return (hasPrice && hasTicketAction) || hasEmptyState;
                    }
                    """,
                    timeout=120_000,
                    polling=1_000,
                )
            except Exception:
                pass

            state = await page.evaluate(
                """
                () => {
                    const text = document.body?.innerText || "";
                    return {
                        title: document.title,
                        url: location.href,
                        bodyTextLength: text.length,
                        skeletonCount: document.querySelectorAll(
                            '[class*="skeleton" i]'
                        ).length,
                        loginPrompt: /ابتدا وارد شوید|ورود یا ثبت.?نام/.test(text),
                        priceCount: (
                            text.match(/[۰-۹0-9][۰-۹0-9,٬.]*\\s*(تومان|ریال)/g) || []
                        ).length,
                        ticketActionCount: (
                            text.match(/(انتخاب|خرید)\\s*(بلیط|پرواز)?/g) || []
                        ).length,
                        emptyState: /(پروازی پیدا نشد|نتیجه‌ای یافت نشد)/.test(text),
                        documentHeight: document.documentElement.scrollHeight,
                    };
                }
                """
            )

            screenshot_path = await capture_page_screenshot(
                page,
                output_dir / "screenshot.png",
            )

            report = {
                "page": state,
                "screenshot_created": screenshot_path is not None,
                "api_responses": response_statuses[-100:],
                "failed_requests": failed_requests[-100:],
            }
            (output_dir / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            diagnosis = json.dumps(report, ensure_ascii=False, indent=2)
            self.assertFalse(
                state["loginPrompt"],
                f"Provider still considers this browser logged out:\n{diagnosis}",
            )
            self.assertTrue(
                state["emptyState"]
                or (state["priceCount"] > 0 and state["ticketActionCount"] > 0),
                f"Flight results never reached a meaningful terminal state:\n{diagnosis}",
            )
            self.assertIsNotNone(
                screenshot_path,
                f"Neither full-page nor viewport screenshot succeeded:\n{diagnosis}",
            )


if __name__ == "__main__":
    unittest.main()
