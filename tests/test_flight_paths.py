"""Airport-code CRUD, real ASGI forms, relational integrity and sample seeding."""

import asyncio
import json
import unittest
from html import escape
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.control.flight_paths import service
from app.control.flight_paths.models import FlightPath
from app.control.main import app
from app.control.websites.models import Website
from app.infra.db import Base, get_db
from app.infra.seeders.flight_paths import seed_flight_paths


class FlightPathTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine, tables=[Website.__table__, FlightPath.__table__]
        )
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as db:
            db.add_all([
                Website(id=1, name="علی‌بابا", base_url="https://www.alibaba.ir"),
                Website(id=2, name="اسنپ‌تریپ", base_url="https://www.snapptrip.com"),
                Website(id=3, name="فلای‌تودی", base_url="https://www.flytoday.ir"),
            ])
            db.flush()
            db.add_all([
                FlightPath(id=1, website_id=1, airport_name_fa="مشهد", code="MHD"),
                FlightPath(id=2, website_id=1, airport_name_fa="تهران", code="THR"),
                FlightPath(id=3, website_id=2, airport_name_fa="مشهد", code="MHD_city"),
            ])
            db.commit()

        def test_db():
            with self.sessions() as db:
                yield db

        previous = app.dependency_overrides.copy()
        self.addCleanup(setattr, app, "dependency_overrides", previous)
        app.dependency_overrides[get_db] = test_db

    async def request(self, method, url, data=None, *, as_json=False):
        body = (
            json.dumps(data, ensure_ascii=False).encode()
            if as_json else urlencode(data or {}, doseq=True).encode()
        )
        content_type = b"application/json" if as_json else b"application/x-www-form-urlencoded"
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

        parts = urlsplit(url)
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": parts.path, "raw_path": parts.path.encode(), "root_path": "",
            "query_string": parts.query.encode(),
            "headers": [(b"host", b"testserver"), (b"content-type", content_type),
                        (b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=5)
        start = next(message for message in messages if message["type"] == "http.response.start")
        text = b"".join(
            message.get("body", b"") for message in messages
            if message["type"] == "http.response.body"
        ).decode()
        return start["status"], dict(start["headers"]), text

    def snapshot(self):
        with self.sessions() as db:
            return list(db.execute(select(
                FlightPath.id, FlightPath.website_id, FlightPath.airport_name_fa, FlightPath.code
            ).order_by(FlightPath.id)))

    async def test_api_full_crud_and_moving_to_a_different_website(self):
        status, _, body = await self.request(
            "POST", "/control/flight-paths",
            {"website_id": 3, "airport_name_fa": "  تهران  ", "code": " thr,1 "},
            as_json=True,
        )
        self.assertEqual(status, 201)
        created = json.loads(body)
        path_id = created["id"]
        self.assertEqual((created["airport_name_fa"], created["code"]), ("تهران", "thr,1"))
        self.assertEqual(created["website"]["name"], "فلای‌تودی")
        self.assertIn("created_at", created)
        status, _, body = await self.request("GET", f"/control/flight-paths/{path_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), created)
        status, _, body = await self.request(
            "PUT", f"/control/flight-paths/{path_id}",
            {"website_id": 2, "airport_name_fa": "تهران", "code": "THR_city"}, as_json=True,
        )
        self.assertEqual(status, 200)
        updated = json.loads(body)
        self.assertEqual(updated["website_id"], 2)
        self.assertEqual(updated["website"]["id"], 2)
        self.assertEqual(updated["code"], "THR_city")
        status, _, body = await self.request("DELETE", f"/control/flight-paths/{path_id}")
        self.assertEqual((status, body), (204, ""))
        status, _, _ = await self.request("GET", f"/control/flight-paths/{path_id}")
        self.assertEqual(status, 404)

    async def test_json_and_html_list_filters(self):
        for suffix, ids in [("", {1, 2, 3}), ("?website_id=1", {1, 2}), ("?website_id=3", set())]:
            status, _, body = await self.request("GET", "/control/flight-paths" + suffix)
            self.assertEqual(status, 200)
            self.assertEqual({row["id"] for row in json.loads(body)}, ids)
        status, headers, body = await self.request("GET", "/control/flight-paths/page?website_id=2")
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn("MHD_city", body)
        self.assertNotIn("/control/flight-paths/page/1/edit", body)
        self.assertIn('value="2" selected', body)
        status, _, _ = await self.request("GET", "/control/flight-paths/page?website_id=")
        self.assertEqual(status, 200)

    async def test_per_website_uniqueness_and_same_mapping_on_other_websites(self):
        original = self.snapshot()
        for payload in [
            {"website_id": 1, "airport_name_fa": "شیراز", "code": "MHD"},
            {"website_id": 1, "airport_name_fa": "مشهد", "code": "NEW"},
        ]:
            status, _, _ = await self.request("POST", "/control/flight-paths", payload, as_json=True)
            self.assertEqual(status, 409)
            self.assertEqual(self.snapshot(), original)
        status, _, body = await self.request(
            "POST", "/control/flight-paths",
            {"website_id": 3, "airport_name_fa": "مشهد", "code": "MHD"}, as_json=True,
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["website_id"], 3)

    async def test_invalid_api_values_leave_rows_unchanged(self):
        original = self.snapshot()
        base = {"website_id": 1, "airport_name_fa": "تهران", "code": "THR"}
        for field, value in [
            ("website_id", 999), ("website_id", 0), ("website_id", "invalid"),
            ("airport_name_fa", "  "), ("airport_name_fa", "ا" * 256),
            ("code", ""), ("code", "  "), ("code", "TH R"),
            ("code", "TH\nR"), ("code", "TH\x00R"), ("code", "x" * 256),
        ]:
            with self.subTest(field=field, value=value):
                status, _, _ = await self.request(
                    "PUT", "/control/flight-paths/2", {**base, field: value}, as_json=True,
                )
                self.assertEqual(status, 422)
                self.assertEqual(self.snapshot(), original)

    async def test_missing_website_creation_is_validation_error(self):
        original = self.snapshot()
        status, _, _ = await self.request(
            "POST", "/control/flight-paths",
            {"website_id": 999, "airport_name_fa": "شیراز", "code": "SYZ"}, as_json=True,
        )
        self.assertEqual(status, 422)
        self.assertEqual(self.snapshot(), original)

    async def test_code_case_punctuation_and_255_character_boundary(self):
        for index, code in enumerate(["THR_city", "thr,1", "mhd", "x" * 255]):
            status, _, body = await self.request(
                "POST", "/control/flight-paths",
                {"website_id": 3, "airport_name_fa": "ف" * 255 if index == 3 else f"فرودگاه {index}",
                 "code": f"  {code}  "}, as_json=True,
            )
            self.assertEqual(status, 201)
            self.assertEqual(json.loads(body)["code"], code)

    async def test_html_create_detail_edit_delete_flow(self):
        status, _, body = await self.request("GET", "/control/flight-paths/page/new?website_id=3")
        self.assertEqual(status, 200)
        self.assertIn('value="3" selected', body)
        status, headers, _ = await self.request(
            "POST", "/control/flight-paths/page/new",
            {"website_id": "3", "airport_name_fa": "تهران", "code": "thr,1"},
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers[b"location"], b"/control/flight-paths/page")
        path_id = self.snapshot()[-1].id
        for suffix in ("", "/edit", "/delete"):
            status, _, body = await self.request("GET", f"/control/flight-paths/page/{path_id}{suffix}")
            self.assertEqual(status, 200)
            self.assertIn("thr,1", body)
        self.assertEqual(len(self.snapshot()), 4)
        status, _, _ = await self.request(
            "POST", f"/control/flight-paths/page/{path_id}/edit",
            {"website_id": "3", "airport_name_fa": "شیراز", "code": "syz,1"},
        )
        self.assertEqual(status, 303)
        self.assertEqual(self.snapshot()[-1].code, "syz,1")
        status, _, _ = await self.request("POST", f"/control/flight-paths/page/{path_id}/delete")
        self.assertEqual(status, 303)
        self.assertEqual(len(self.snapshot()), 3)

    async def test_invalid_forms_preserve_values_and_escape_html(self):
        original = self.snapshot()
        unsafe_name = '\"><script>alert("test")</script>'
        for website_id, name, code, expected in [
            ("1", unsafe_name, "MHD", 409),
            ("999", "شیراز", "SYZ", 422),
            ("wrong", "شیراز", "SYZ", 422),
            ("", "شیراز", "SYZ", 422),
            ("1", "", "SYZ", 422),
            ("1", "شیراز", "S YZ", 422),
            ("1", "شیراز", "x" * 256, 422),
        ]:
            for url in ("/control/flight-paths/page/new", "/control/flight-paths/page/2/edit"):
                with self.subTest(website_id=website_id, name=name, code=code, url=url):
                    status, headers, body = await self.request(
                        "POST", url,
                        {"website_id": website_id, "airport_name_fa": name, "code": code},
                    )
                    self.assertEqual(status, expected)
                    self.assertIn(b"text/html", headers[b"content-type"])
                    self.assertIn(f'value="{escape(name).replace("&quot;", "&#34;")}"', body)
                    self.assertIn(f'value="{code}"', body)
                    if website_id:
                        self.assertIn(f'value="{website_id}" selected', body)
                    self.assertNotIn('<script>alert("test")</script>', body)
                    self.assertEqual(self.snapshot(), original)

    async def test_no_websites_explains_required_first_step(self):
        with self.sessions() as db:
            db.query(FlightPath).delete()
            db.query(Website).delete()
            db.commit()
        for path in ("/control/flight-paths/page", "/control/flight-paths/page/new"):
            status, _, body = await self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn("ابتدا یک وب‌سایت اضافه کنید", body)
            self.assertIn("/control/websites/page/new", body)
            self.assertNotIn('name="airport_name_fa"', body)

    async def test_unknown_records_return_404_for_all_actions(self):
        payload = {"website_id": 1, "airport_name_fa": "شیراز", "code": "SYZ"}
        for method, suffix, as_json in [
            ("GET", "/999", False), ("PUT", "/999", True), ("DELETE", "/999", False),
            ("GET", "/page/999", False), ("GET", "/page/999/edit", False),
            ("POST", "/page/999/edit", False), ("GET", "/page/999/delete", False),
            ("POST", "/page/999/delete", False),
        ]:
            with self.subTest(method=method, suffix=suffix):
                status, _, _ = await self.request(method, "/control/flight-paths" + suffix, payload, as_json=as_json)
                self.assertEqual(status, 404)

    async def test_website_delete_is_blocked_until_dependent_codes_removed(self):
        original = self.snapshot()
        status, _, body = await self.request("DELETE", "/control/websites/1")
        self.assertEqual(status, 409)
        self.assertEqual(self.snapshot(), original)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(Website, 1))
        for path_id in (1, 2):
            status, _, _ = await self.request("DELETE", f"/control/flight-paths/{path_id}")
            self.assertEqual(status, 204)
        status, _, _ = await self.request("DELETE", "/control/websites/1")
        self.assertEqual(status, 204)
        self.assertEqual([row.id for row in self.snapshot()], [3])

    def test_database_enforces_fk_and_both_unique_keys(self):
        original = self.snapshot()
        with self.sessions() as db:
            for website_id, name, code in [(999, "فرودگاه", "NEW"), (1, "فرودگاه", "MHD"), (1, "مشهد", "NEW")]:
                db.add(FlightPath(website_id=website_id, airport_name_fa=name, code=code))
                with self.assertRaises(IntegrityError):
                    db.commit()
                db.rollback()
            db.delete(db.get(Website, 1))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            self.assertIsNotNone(db.get(Website, 1))
        self.assertEqual(self.snapshot(), original)

    def test_failed_update_rolls_back_and_session_can_be_reused(self):
        original = self.snapshot()
        with self.sessions() as db:
            with self.assertRaises(service.FlightPathAlreadyExistsError):
                service.update_flight_path(db, 2, 1, "نام جدید", "MHD")
            self.assertEqual(self.snapshot(), original)
            saved = service.update_flight_path(db, 2, 1, "تهران مهرآباد", "THR")
            self.assertEqual(saved.airport_name_fa, "تهران مهرآباد")

    def test_sample_seeder_repeats_without_overwriting_manual_changes(self):
        with patch("app.infra.seeders.flight_paths.get_seed_session", self.sessions):
            seed_flight_paths()
            first = self.snapshot()
            self.assertEqual(len(first), 6)
            seed_flight_paths()
            self.assertEqual(self.snapshot(), first)
            with self.sessions() as db:
                db.get(FlightPath, 1).code = "custom_mashhad"
                db.get(FlightPath, 2).airport_name_fa = "تهران مهرآباد"
                db.commit()
            modified = self.snapshot()
            seed_flight_paths()
            self.assertEqual(self.snapshot(), modified)

    def test_missing_website_seed_failure_is_atomic(self):
        with self.sessions() as db:
            db.query(FlightPath).delete()
            db.delete(db.get(Website, 3))
            db.commit()
        with patch("app.infra.seeders.flight_paths.get_seed_session", self.sessions):
            with self.assertRaisesRegex(ValueError, "Seed websites first"):
                seed_flight_paths()
        self.assertEqual(self.snapshot(), [])


if __name__ == "__main__":
    unittest.main()
