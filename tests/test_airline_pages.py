"""Exercise the real ASGI routes and forms without a live database or HTTP client."""

import asyncio
import json
import unittest
from html import escape
from urllib.parse import urlencode

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.control.airlines.models import Airline, AirlineAlias
from app.control.main import app
from app.infra.db import Base, get_db


class AirlinePageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(
            self.engine, tables=[Airline.__table__, AirlineAlias.__table__]
        )
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as db:
            db.add_all([
                Airline(
                    id=1,
                    official_name_fa="ایران ایر",
                    aliases=[AirlineAlias(alias_name="Homa")],
                ),
                Airline(id=2, official_name_fa="ماهان"),
            ])
            db.commit()

        def test_db():
            with self.sessions() as db:
                yield db

        previous_overrides = app.dependency_overrides.copy()
        self.addCleanup(setattr, app, "dependency_overrides", previous_overrides)
        app.dependency_overrides[get_db] = test_db

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
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", content_type),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        start = next(m for m in messages if m["type"] == "http.response.start")
        text = b"".join(
            m.get("body", b"") for m in messages if m["type"] == "http.response.body"
        ).decode()
        return start["status"], dict(start["headers"]), text

    def assert_original_airline(self):
        with self.sessions() as db:
            airline = db.get(Airline, 1)
            self.assertEqual(airline.official_name_fa, "ایران ایر")
            self.assertEqual([a.alias_name for a in airline.aliases], ["Homa"])

    async def test_list_page_renders_html_instead_of_matching_id_route(self):
        status, headers, body = await self.request("GET", "/control/airlines/page")
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn("ایران ایر", body)
        self.assertIn("Homa", body)
        self.assertIn("/control/airlines/page/1/edit", body)

    async def test_empty_list_page(self):
        with self.sessions() as db:
            for airline in db.scalars(select(Airline)).all():
                db.delete(airline)
            db.commit()
        status, _, body = await self.request("GET", "/control/airlines/page")
        self.assertEqual(status, 200)
        self.assertIn("هیچ ایرلاینی ثبت نشده است.", body)

    async def test_edit_form_is_prefilled(self):
        status, _, body = await self.request("GET", "/control/airlines/page/1/edit")
        self.assertEqual(status, 200)
        self.assertIn('value="ایران ایر"', body)
        self.assertIn('value="Homa"', body)

    async def test_unchanged_save_redirects_to_working_list(self):
        status, headers, _ = await self.request(
            "POST", "/control/airlines/page/1/edit",
            {"official_name_fa": "ایران ایر", "aliases": ["Homa"]},
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"], b"/control/airlines/page")
        self.assert_original_airline()
        status, _, _ = await self.request("GET", headers[b"location"].decode())
        self.assertEqual(status, 200)

    async def test_form_saves_repeated_alias_fields_and_normalizes_them(self):
        status, _, _ = await self.request(
            "POST", "/control/airlines/page/1/edit",
            {"official_name_fa": "  ایران‌ایر  ", "aliases": ["Homa", " IR ", "IR", ""]},
        )
        self.assertEqual(status, 303)
        with self.sessions() as db:
            airline = db.get(Airline, 1)
            self.assertEqual(airline.official_name_fa, "ایران‌ایر")
            self.assertEqual({a.alias_name for a in airline.aliases}, {"Homa", "IR"})

    async def test_form_can_remove_all_aliases(self):
        status, _, _ = await self.request(
            "POST", "/control/airlines/page/1/edit", {"official_name_fa": "ایران ایر"},
        )
        self.assertEqual(status, 303)
        with self.sessions() as db:
            self.assertEqual(db.get(Airline, 1).aliases, [])

    async def test_duplicate_name_preserves_submitted_values_and_database(self):
        status, _, body = await self.request(
            "POST", "/control/airlines/page/1/edit",
            {"official_name_fa": "ماهان", "aliases": ["New alias", "Homa"]},
        )
        self.assertEqual(status, 409)
        self.assertIn("ایرلاینی با این نام از قبل وجود دارد.", body)
        self.assertIn('value="ماهان"', body)
        self.assertIn('value="New alias"', body)
        self.assert_original_airline()

    async def test_empty_missing_and_whitespace_names_show_html_errors(self):
        for name in (None, "", "  ", "\t"):
            with self.subTest(name=name):
                data = {"aliases": ["New alias"]}
                if name is not None:
                    data["official_name_fa"] = name
                status, headers, body = await self.request(
                    "POST", "/control/airlines/page/1/edit", data,
                )
                self.assertEqual(status, 422)
                self.assertIn(b"text/html", headers[b"content-type"])
                self.assertIn("نام رسمی فارسی نمی‌تواند خالی باشد.", body)
                self.assertIn('value="New alias"', body)
                self.assert_original_airline()

    async def test_oversize_form_values_are_rejected_and_preserved(self):
        for name, aliases in [("ا" * 256, ["New alias"]), ("نام جدید", ["x" * 256])]:
            with self.subTest(name_length=len(name)):
                status, _, body = await self.request(
                    "POST", "/control/airlines/page/1/edit",
                    {"official_name_fa": name, "aliases": aliases},
                )
                self.assertEqual(status, 422)
                self.assertIn(f'value="{name}"', body)
                self.assertIn(f'value="{aliases[0]}"', body)
                self.assert_original_airline()

    async def test_submitted_html_is_escaped_on_error(self):
        alias = '\"><script>alert("test")</script>'
        status, _, body = await self.request(
            "POST", "/control/airlines/page/1/edit",
            {"official_name_fa": "ماهان", "aliases": [alias]},
        )
        self.assertEqual(status, 409)
        self.assertNotIn('<script>alert("test")</script>', body)
        self.assertIn(escape(alias).replace("&quot;", "&#34;"), body)

    async def test_unknown_airlines_return_404(self):
        for method, path, as_json in [
            ("GET", "/control/airlines/99999", False),
            ("GET", "/control/airlines/page/99999/edit", False),
            ("POST", "/control/airlines/page/99999/edit", False),
            ("PUT", "/control/airlines/99999", True),
            ("DELETE", "/control/airlines/99999", False),
            ("GET", "/control/airlines/page/99999", False),
            ("GET", "/control/airlines/page/99999/delete", False),
            ("POST", "/control/airlines/page/99999/delete", False),
        ]:
            with self.subTest(method=method, path=path):
                status, _, _ = await self.request(
                    method, path,
                    {"official_name_fa": "ایران ایر", "aliases": []}, as_json=as_json,
                )
                self.assertEqual(status, 404)

    async def test_api_list_and_detail_remain_json(self):
        status, headers, body = await self.request("GET", "/control/airlines")
        self.assertEqual(status, 200)
        self.assertIn(b"application/json", headers[b"content-type"])
        self.assertEqual(len(json.loads(body)), 2)
        status, _, body = await self.request("GET", "/control/airlines/1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["aliases"][0]["alias_name"], "Homa")

    async def test_api_update_and_duplicate_name(self):
        status, _, body = await self.request(
            "PUT", "/control/airlines/1",
            {"official_name_fa": "  ایران ایر  ", "aliases": [" Homa "]}, as_json=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["official_name_fa"], "ایران ایر")
        self.assert_original_airline()
        status, _, _ = await self.request(
            "PUT", "/control/airlines/1",
            {"official_name_fa": "ماهان", "aliases": ["New alias"]}, as_json=True,
        )
        self.assertEqual(status, 409)
        self.assert_original_airline()

    async def test_api_rejects_invalid_names_and_aliases(self):
        for payload in [
            {"official_name_fa": ""},
            {"official_name_fa": "  "},
            {"official_name_fa": "ا" * 256},
            {"official_name_fa": "ایران ایر", "aliases": ["x" * 256]},
            {"official_name_fa": "نام\x00جدید"},
            {"official_name_fa": "ایران ایر", "aliases": ["new\x00alias"]},
        ]:
            with self.subTest(payload=payload):
                status, _, _ = await self.request(
                    "PUT", "/control/airlines/1", payload, as_json=True,
                )
                self.assertEqual(status, 422)
                self.assert_original_airline()

    async def test_create_page_and_list_link(self):
        status, _, body = await self.request("GET", "/control/airlines/page")
        self.assertEqual(status, 200)
        self.assertIn('/control/airlines/page/new', body)
        status, _, body = await self.request("GET", "/control/airlines/page/new")
        self.assertEqual(status, 200)
        self.assertIn("افزودن ایرلاین", body)
        self.assertIn('action="/control/airlines/page/new"', body)

    async def test_create_form_saves_then_redirects(self):
        status, headers, _ = await self.request(
            "POST", "/control/airlines/page/new",
            {"official_name_fa": " کیش ایر ", "aliases": [" Kish Air ", "Kish Air", ""]},
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"], b"/control/airlines/page")
        with self.sessions() as db:
            airline = db.scalar(select(Airline).where(Airline.official_name_fa == "کیش ایر"))
            self.assertIsNotNone(airline)
            self.assertEqual([alias.alias_name for alias in airline.aliases], ["Kish Air"])

    async def test_create_form_validation_preserves_inputs(self):
        for name, expected_status in [("ماهان", 409), ("  ", 422), ("ا" * 256, 422)]:
            with self.subTest(name=name):
                status, headers, body = await self.request(
                    "POST", "/control/airlines/page/new",
                    {"official_name_fa": name, "aliases": ["New alias"]},
                )
                self.assertEqual(status, expected_status)
                self.assertIn(b"text/html", headers[b"content-type"])
                self.assertIn(f'value="{name}"', body)
                self.assertIn('value="New alias"', body)
                self.assertIn('action="/control/airlines/page/new"', body)
                self.assert_original_airline()
                with self.sessions() as db:
                    self.assertEqual(len(list(db.scalars(select(Airline)))), 2)

    async def test_detail_and_delete_confirmation_do_not_mutate(self):
        status, _, body = await self.request("GET", "/control/airlines/page/1")
        self.assertEqual(status, 200)
        self.assertIn("ایران ایر", body)
        self.assertIn("Homa", body)
        self.assertIn('/control/airlines/page/1/delete', body)
        status, _, body = await self.request("GET", "/control/airlines/page/1/delete")
        self.assertEqual(status, 200)
        self.assertIn("ایران ایر", body)
        self.assertIn('method="post"', body)
        self.assert_original_airline()

    async def test_delete_form_removes_airline_and_aliases(self):
        status, headers, _ = await self.request("POST", "/control/airlines/page/1/delete")
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"], b"/control/airlines/page")
        with self.sessions() as db:
            self.assertIsNone(db.get(Airline, 1))
            self.assertEqual(list(db.scalars(select(AirlineAlias))), [])
            self.assertIsNotNone(db.get(Airline, 2))

    async def test_api_create_read_and_delete(self):
        status, _, body = await self.request(
            "POST", "/control/airlines",
            {"official_name_fa": " کیش ایر ", "aliases": ["Kish Air", " Kish Air "]},
            as_json=True,
        )
        self.assertEqual(status, 201)
        airline = json.loads(body)
        self.assertEqual(airline["official_name_fa"], "کیش ایر")
        self.assertEqual(len(airline["aliases"]), 1)
        status, _, body = await self.request("GET", f'/control/airlines/{airline["id"]}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), airline)
        status, _, body = await self.request("DELETE", f'/control/airlines/{airline["id"]}')
        self.assertEqual(status, 204)
        self.assertEqual(body, "")
        status, _, _ = await self.request("GET", f'/control/airlines/{airline["id"]}')
        self.assertEqual(status, 404)
        with self.sessions() as db:
            self.assertEqual(
                list(db.scalars(select(AirlineAlias).where(AirlineAlias.airline_id == airline["id"]))),
                [],
            )

    async def test_api_create_duplicate_and_invalid_payloads(self):
        for payload, expected_status in [
            ({"official_name_fa": "ماهان"}, 409),
            ({"official_name_fa": " "}, 422),
            ({"official_name_fa": "ا" * 256}, 422),
            ({"official_name_fa": "کیش ایر", "aliases": ["x" * 256]}, 422),
            ({"official_name_fa": "نام\x00جدید"}, 422),
            ({"official_name_fa": "کیش ایر", "aliases": ["new\x00alias"]}, 422),
            ({"aliases": []}, 422),
        ]:
            with self.subTest(payload=payload):
                status, _, _ = await self.request("POST", "/control/airlines", payload, as_json=True)
                self.assertEqual(status, expected_status)
                self.assert_original_airline()


if __name__ == "__main__":
    unittest.main()
