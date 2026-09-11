"""Website CRUD, validation, deletion constraints and editable HTML forms."""

import asyncio
import json
import unittest
from html import escape
from urllib.parse import urlencode

from fastapi import FastAPI
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.control.flight_paths.models import FlightPath
from app.control.websites import service
from app.control.websites.api import router
from app.control.websites.models import Website
from app.control.websites.schemas import normalize_base_url
from app.infra.db import Base, get_db
from app.infra.seeders.websites import WEBSITES, seed_websites


class WebsiteDatabaseMixin:
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[Website.__table__, FlightPath.__table__])
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as db:
            db.add_all([
                Website(id=1, name="علی‌بابا", base_url="https://www.alibaba.ir"),
                Website(id=2, name="فلای‌تودی", base_url="https://www.flytoday.ir"),
            ])
            db.commit()

    def add_flight_path(self):
        with self.sessions() as db:
            db.add(FlightPath(website_id=1, airport_name_fa="مشهد", code="MHD"))
            db.commit()


class WebsiteServiceTests(WebsiteDatabaseMixin, unittest.TestCase):
    def test_normalizes_origin(self):
        for source, expected in [
            (" HTTPS://WWW.ALIBABA.IR:443/ ", "https://www.alibaba.ir"),
            ("http://Example.com:80", "http://example.com"),
            ("https://example.com:8443/", "https://example.com:8443"),
        ]:
            self.assertEqual(normalize_base_url(source), expected)

    def test_rejects_non_origin_urls(self):
        for value in (
            "", "example.com", "javascript:alert(1)", "ftp://example.com",
            "https:example.com", "https:///example.com", "https://example.com/flights",
            "https://example.com/a/..", "https://user:pass@example.com",
            "https://@example.com", "https://example.com?x=1", "https://example.com?",
            "https://example.com/#", "https://exam ple.com", "https://exa\nmple.com",
            "https://example.com\\", "https://example.com:99999", "https://[",
            "https://example.com\x00", "https://exa\x7fmple.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_base_url(value)

    def test_service_crud_and_session_recovery_after_conflict(self):
        with self.sessions() as db:
            website = service.create_website(db, "  نمونه  ", "HTTPS://EXAMPLE.COM:443/")
            website_id = website.id
            self.assertEqual(website.name, "نمونه")
            self.assertEqual(website.base_url, "https://example.com")
            with self.assertRaises(service.WebsiteAlreadyExistsError):
                service.update_website(db, website_id, "علی‌بابا", "https://other.example")
            self.assertEqual(service.get_website(db, website_id).name, "نمونه")
            website = service.update_website(db, website_id, "نمونه دوم", "https://other.example/")
            self.assertEqual(website.base_url, "https://other.example")
            service.delete_website(db, website_id)
            with self.assertRaises(service.WebsiteNotFoundError):
                service.get_website(db, website_id)

    def test_validation_does_not_partially_change_persistent_fields(self):
        with self.sessions() as db:
            with self.assertRaises(ValueError):
                service.update_website(db, 1, "نام تغییر یافته", "invalid")
            db.commit()
            self.assertEqual(db.get(Website, 1).name, "علی‌بابا")

    def test_dependent_path_blocks_delete_and_session_remains_usable(self):
        self.add_flight_path()
        with self.sessions() as db:
            with self.assertRaises(service.WebsiteInUseError):
                service.delete_website(db, 1)
            self.assertEqual(service.get_website(db, 1).name, "علی‌بابا")
            self.assertIsNotNone(db.scalar(select(FlightPath)))
            service.update_website(db, 1, "علی‌بابای جدید", "https://www.alibaba.ir")

    def test_seeder_is_idempotent_and_preserves_user_values(self):
        with self.sessions() as db:
            db.get(Website, 1).name = "نام سفارشی علی‌بابا"
            db.get(Website, 2).base_url = "https://custom.example"
            db.commit()
            seed_websites(db)
            seed_websites(db)
            self.assertEqual(len(service.get_websites(db)), len(WEBSITES))
            self.assertEqual(db.get(Website, 1).name, "نام سفارشی علی‌بابا")
            self.assertEqual(db.get(Website, 2).base_url, "https://custom.example")


class WebsiteRouteTests(WebsiteDatabaseMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(router)

        def test_db():
            with self.sessions() as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db

    async def request(self, method, path, data=None, *, as_json=False):
        if as_json:
            body = json.dumps(data, ensure_ascii=False).encode()
            content_type = b"application/json"
        else:
            body = urlencode(data or {}, doseq=True).encode()
            content_type = b"application/x-www-form-urlencoded"
        messages = []
        received = False

        async def receive():
            nonlocal received
            if received:
                await asyncio.Event().wait()
            received = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "headers": [(b"host", b"testserver"), (b"content-type", content_type),
                        (b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
        }
        await asyncio.wait_for(self.app(scope, receive, send), timeout=5)
        start = next(message for message in messages if message["type"] == "http.response.start")
        text = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        ).decode()
        return start["status"], dict(start["headers"]), text

    async def test_json_crud(self):
        status, _, body = await self.request("GET", "/control/websites")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)), 2)
        status, _, body = await self.request(
            "POST", "/control/websites", {"name": "  نمونه  ", "base_url": "HTTPS://EXAMPLE.COM:443/"}, as_json=True,
        )
        self.assertEqual(status, 201)
        website = json.loads(body)
        self.assertEqual(website["name"], "نمونه")
        self.assertEqual(website["base_url"], "https://example.com")
        self.assertTrue(website["created_at"])
        path = f'/control/websites/{website["id"]}'
        status, _, body = await self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), website)
        status, _, body = await self.request(
            "PUT", path, {"name": "نام تازه", "base_url": "https://new.example"}, as_json=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["name"], "نام تازه")
        status, _, body = await self.request("DELETE", path)
        self.assertEqual((status, body), (204, ""))
        status, _, _ = await self.request("GET", path)
        self.assertEqual(status, 404)

    async def test_duplicate_name_or_normalized_origin_returns_409(self):
        for data in (
            {"name": "علی‌بابا", "base_url": "https://another.example"},
            {"name": "نام جدید", "base_url": "HTTPS://WWW.ALIBABA.IR:443/"},
        ):
            for method, path in (("POST", "/control/websites"), ("PUT", "/control/websites/2")):
                with self.subTest(data=data, method=method):
                    status, _, _ = await self.request(method, path, data, as_json=True)
                    self.assertEqual(status, 409)
        with self.sessions() as db:
            self.assertEqual(len(service.get_websites(db)), 2)
            self.assertEqual(db.get(Website, 2).name, "فلای‌تودی")

    async def test_invalid_json_returns_422(self):
        for data in (
            {}, {"name": " ", "base_url": "https://example.com"},
            {"name": "x" * 256, "base_url": "https://example.com"},
            {"name": "نمونه", "base_url": "https://example.com/flights"},
            {"name": "نمونه", "base_url": "javascript:alert(1)"},
            {"name": None, "base_url": "https://example.com"},
            {"name": "نام\x00وب‌سایت", "base_url": "https://example.com"},
            {"name": "نمونه", "base_url": "https://example.com\x00"},
        ):
            with self.subTest(data=data):
                status, _, _ = await self.request("POST", "/control/websites", data, as_json=True)
                self.assertEqual(status, 422)

    async def test_html_pages_render_and_delete_get_does_not_mutate(self):
        for path, expected in (
            ("/control/websites/page", "افزودن وب‌سایت"),
            ("/control/websites/page/new", 'name="base_url"'),
            ("/control/websites/page/1", "علی‌بابا"),
            ("/control/websites/page/1/edit", 'value="https://www.alibaba.ir"'),
            ("/control/websites/page/1/delete", "تأیید حذف وب‌سایت"),
        ):
            with self.subTest(path=path):
                status, headers, body = await self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(b"text/html", headers[b"content-type"])
                self.assertIn(expected, body)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Website, 1))

    async def test_html_create_edit_and_delete(self):
        status, headers, _ = await self.request(
            "POST", "/control/websites/page/new", {"name": "نمونه", "base_url": "https://example.com/"},
        )
        self.assertEqual(status, 303)
        detail_path = headers[b"location"].decode()
        status, _, _ = await self.request("GET", detail_path)
        self.assertEqual(status, 200)
        status, headers, _ = await self.request(
            "POST", detail_path + "/edit", {"name": "ویرایش شده", "base_url": "https://new.example/"},
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"].decode(), detail_path)
        status, _, body = await self.request("GET", detail_path)
        self.assertIn("ویرایش شده", body)
        status, headers, _ = await self.request("POST", detail_path + "/delete")
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"], b"/control/websites/page")
        status, _, _ = await self.request("GET", detail_path)
        self.assertEqual(status, 404)

    async def test_invalid_form_preserves_raw_values_and_escapes_html(self):
        name = '<script>alert("test")</script>'
        for path in ("/control/websites/page/new", "/control/websites/page/1/edit"):
            status, headers, body = await self.request("POST", path, {"name": name, "base_url": "invalid URL"})
            self.assertEqual(status, 422)
            self.assertIn(b"text/html", headers[b"content-type"])
            self.assertIn('value="invalid URL"', body)
            self.assertNotIn(name, body)
            self.assertIn(escape(name).replace("&quot;", "&#34;"), body)
        with self.sessions() as db:
            self.assertEqual(db.get(Website, 1).name, "علی‌بابا")

    async def test_duplicate_form_preserves_submitted_values(self):
        for path in ("/control/websites/page/new", "/control/websites/page/2/edit"):
            status, _, body = await self.request(
                "POST", path, {"name": "علی‌بابا", "base_url": "https://another.example/"},
            )
            self.assertEqual(status, 409)
            self.assertIn(service.DUPLICATE_MESSAGE, body)
            self.assertIn('value="https://another.example/"', body)

    async def test_empty_form_shows_html_validation(self):
        status, headers, body = await self.request("POST", "/control/websites/page/new")
        self.assertEqual(status, 422)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn("نام وب‌سایت نمی‌تواند خالی باشد.", body)

    async def test_form_rejects_embedded_control_characters(self):
        for data in (
            {"name": "نام\x00وب‌سایت", "base_url": "https://example.com"},
            {"name": "نام وب‌سایت", "base_url": "https://exa\x7fmple.com"},
        ):
            status, headers, _ = await self.request("POST", "/control/websites/page/new", data)
            self.assertEqual(status, 422)
            self.assertIn(b"text/html", headers[b"content-type"])

    async def test_website_with_paths_cannot_be_deleted_via_api_or_form(self):
        self.add_flight_path()
        for method, path in (("DELETE", "/control/websites/1"), ("POST", "/control/websites/page/1/delete")):
            status, _, body = await self.request(method, path)
            self.assertEqual(status, 409)
            self.assertIn(service.IN_USE_MESSAGE, body)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Website, 1))
            self.assertIsNotNone(db.scalar(select(FlightPath)))

    async def test_missing_websites_return_404(self):
        for method, path, as_json in (
            ("GET", "/control/websites/99999", False),
            ("PUT", "/control/websites/99999", True),
            ("DELETE", "/control/websites/99999", False),
            ("GET", "/control/websites/page/99999", False),
            ("GET", "/control/websites/page/99999/edit", False),
            ("POST", "/control/websites/page/99999/edit", False),
            ("GET", "/control/websites/page/99999/delete", False),
            ("POST", "/control/websites/page/99999/delete", False),
        ):
            with self.subTest(method=method, path=path):
                status, _, _ = await self.request(
                    method, path, {"name": "نمونه", "base_url": "https://example.com"}, as_json=as_json,
                )
                self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
