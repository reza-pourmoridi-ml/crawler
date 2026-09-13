import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.control.airports.models import Airport
from app.control.search_box.api import (
    create_search_request_page,
    search_box_page,
    search_results_page,
)
from app.control.search_box.jalali import jalali_to_gregorian
from app.control.search_box.models import (
    SearchRequest,
)
from app.infra.db import Base


class SearchBoxPageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(
            self.engine,
            tables=[
                Airport.__table__,
                SearchRequest.__table__,
            ],
        )
        with Session(self.engine) as db:
            db.add_all([
                Airport(id=1, name_fa="تهران", category="domestic"),
                Airport(id=2, name_fa="مشهد", category="domestic"),
            ])
            db.commit()

    @staticmethod
    def request(path: str) -> Request:
        return Request({
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
        })

    def create_request(self, request_id=1):
        with Session(self.engine) as db:
            db.add(SearchRequest(
                id=request_id,
                route_type="domestic",
                origin_airport_id=1,
                destination_airport_id=2,
                departure_date=date(2026, 9, 20),
            ))
            db.commit()

    def test_search_page_uses_three_date_selects_and_results_link(self):
        self.create_request()
        with Session(self.engine) as db, patch(
            "app.control.search_box.api.get_search_results",
            return_value={1: {
                "status": "waiting", "updated_at": None, "offers": [], "providers": [],
            }},
        ):
            response = search_box_page(self.request("/control/search-box/page"), db=db)
        body = response.body.decode()
        self.assertIn('name="departure_day"', body)
        self.assertIn('name="departure_month"', body)
        self.assertIn('name="departure_year"', body)
        self.assertNotIn('name="departure_date_jalali"', body)
        self.assertIn('/control/search-box/page/1/results', body)
        self.assertIn('دیدن نتایج', body)
        self.assertIn('window.setInterval(refreshRequests, 5000)', body)

    def test_three_date_parts_create_the_same_existing_search_request(self):
        with Session(self.engine) as db:
            response = create_search_request_page(
                self.request("/control/search-box/page"),
                route_type="domestic",
                origin_airport_id=1,
                destination_airport_id=2,
                departure_date_jalali="",
                departure_year=1405,
                departure_month=6,
                departure_day=29,
                db=db,
            )
            saved = db.scalar(select(SearchRequest))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(saved.departure_date, jalali_to_gregorian(1405, 6, 29))

    def test_results_page_is_separate_and_auto_refreshes(self):
        self.create_request(7)
        result = {
            "search_request_id": 7,
            "status": "partial",
            "updated_at": None,
            "offers": [],
            "providers": [
                {"website_id": 1, "website_name": "فروشنده یک", "status": "ready", "offers_count": 1, "updated_at": None},
                {"website_id": 2, "website_name": "فروشنده دو", "status": "processing", "offers_count": 1, "updated_at": None},
            ],
        }
        provider_prices = [
            {"airline": "ماهان", "website_id": 1, "price": 3_000_000, "time": "10:00"},
            {"airline": "ماهان", "website_id": 2, "price": 2_500_000, "time": "14:00"},
        ]
        with Session(self.engine) as db, \
             patch("app.control.search_box.api.get_search_result", return_value=result), \
             patch("app.control.search_box.api.get_provider_airline_prices", return_value=provider_prices):
            response = search_results_page(
                self.request("/control/search-box/page/7/results"),
                search_request_id=7,
                db=db,
            )
        body = response.body.decode()
        self.assertIn("نتایج جستجوی پرواز", body)
        self.assertIn("تهران به مشهد", body)
        self.assertIn('id="search-result-content"', body)
        self.assertIn("فروشنده یک", body)
        self.assertIn("فروشنده دو", body)
        self.assertIn("3,000,000", body)
        self.assertIn("2,500,000", body)
        self.assertNotIn("<th>فروشنده</th>", body)
        self.assertNotIn("<th>زمان به‌روزرسانی</th>", body)
        self.assertIn('window.setInterval(refreshResults, 5000)', body)


if __name__ == "__main__":
    unittest.main()
