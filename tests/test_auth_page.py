import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.datastructures import UploadFile
from starlette.requests import Request

from app.control.auth.api import auth_page, upload_auth_page
from app.infra.config import settings


class AuthPageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.auth_path = self.root / "auth" / "auth.json"
        setting_patch = patch.object(settings, "auth_state_file", str(self.auth_path))
        setting_patch.start()
        self.addCleanup(setting_patch.stop)

    @staticmethod
    def request(method="GET") -> Request:
        return Request({
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": "/control/auth/page",
            "raw_path": b"/control/auth/page",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
        })

    def upload(self, content: bytes):
        upload = UploadFile(io.BytesIO(content), filename="auth.json")
        return asyncio.run(upload_auth_page(self.request("POST"), upload))

    def test_valid_playwright_storage_state_is_atomically_uploaded(self):
        state = {
            "cookies": [{"name": "session", "value": "private-token"}],
            "origins": [{"origin": "https://example.test", "localStorage": []}],
        }
        response = self.upload(json.dumps(state).encode())

        self.assertEqual(response.status_code, 303)
        self.assertEqual(json.loads(self.auth_path.read_text()), state)
        self.assertEqual(list(self.auth_path.parent.glob(".atomic-*.tmp")), [])

        page = auth_page(self.request())
        body = page.body.decode()
        self.assertIn("موجود است", body)
        self.assertIn("آخرین به‌روزرسانی", body)
        self.assertNotIn("private-token", body)

    def test_invalid_json_is_rejected_without_replacing_existing_auth(self):
        original = b'{"cookies": [], "origins": []}'
        self.auth_path.parent.mkdir(parents=True)
        self.auth_path.write_bytes(original)

        response = self.upload(b'{"cookies": ["secret-value"],')

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.auth_path.read_bytes(), original)
        self.assertIn("JSON معتبر نیست", response.body.decode())
        self.assertNotIn("secret-value", response.body.decode())

    def test_non_playwright_json_is_rejected(self):
        response = self.upload(b'{"cookies": [], "origins": {}}')
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.auth_path.exists())


if __name__ == "__main__":
    unittest.main()
