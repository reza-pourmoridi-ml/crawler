import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.scraper import service


class _PlaywrightContext:
    def __init__(self, playwright):
        self.playwright = playwright

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ScraperAuthStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrape_loads_auth_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth_path = root / "auth.json"
            original_auth = b'{"cookies": [], "origins": []}'
            auth_path.write_bytes(original_auth)

            page = Mock()
            page.url = "https://example.test/results"
            page.goto = AsyncMock()
            page.screenshot = AsyncMock()
            page.on = Mock()

            context = Mock()
            context.add_init_script = AsyncMock()
            context.new_page = AsyncMock(return_value=page)
            context.storage_state = AsyncMock()

            browser = Mock()
            browser.new_context = AsyncMock(return_value=context)
            browser.close = AsyncMock()

            chromium = Mock()
            chromium.launch = AsyncMock(return_value=browser)
            playwright = Mock(chromium=chromium)

            with (
                patch.object(service, "AUTH_STATE_FILE", auth_path),
                patch.object(
                    service,
                    "async_playwright",
                    return_value=_PlaywrightContext(playwright),
                ),
                patch.object(service, "wait_for_page_stability", new=AsyncMock()),
                patch.object(service.asyncio, "sleep", new=AsyncMock()),
                patch.object(
                    service,
                    "wait_for_manual_resolution_if_needed",
                    new=AsyncMock(return_value="clean"),
                ),
                patch.object(service, "human_like_scroll", new=AsyncMock()),
                patch.object(
                    service,
                    "extract_clean_html",
                    new=AsyncMock(return_value="<html></html>"),
                ),
                patch.object(
                    service,
                    "extract_visible_texts_with_ids",
                    new=AsyncMock(return_value=[]),
                ),
            ):
                result = await service.scrape_url(
                    "https://example.test/search",
                    root / "output",
                )

            self.assertEqual(result["status"], "success")
            self.assertEqual(
                browser.new_context.await_args.kwargs["storage_state"],
                str(auth_path),
            )
            context.storage_state.assert_not_awaited()
            self.assertEqual(auth_path.read_bytes(), original_auth)

    async def test_full_page_timeout_falls_back_to_viewport(self):
        page = Mock()
        page.screenshot = AsyncMock(
            side_effect=[service.PlaywrightTimeoutError("timeout"), None]
        )
        path = Path("screenshot.png")

        result = await service.capture_page_screenshot(page, path)

        self.assertEqual(result, path)
        self.assertEqual(page.screenshot.await_count, 2)
        self.assertTrue(page.screenshot.await_args_list[0].kwargs["full_page"])
        self.assertFalse(page.screenshot.await_args_list[1].kwargs["full_page"])

    async def test_screenshot_failure_is_not_fatal(self):
        page = Mock()
        page.screenshot = AsyncMock(side_effect=RuntimeError("capture failed"))

        result = await service.capture_page_screenshot(
            page,
            Path("screenshot.png"),
        )

        self.assertIsNone(result)
        self.assertEqual(page.screenshot.await_count, 2)


if __name__ == "__main__":
    unittest.main()
