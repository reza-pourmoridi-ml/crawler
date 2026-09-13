import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.control.airlines.models import Airline
from app.control.airports.models import Airport
from app.control.search_box.models import (
    SearchAirlinePrice,
    SearchLowestPrice,
    SearchProviderResult,
    SearchRequest,
)
from app.control.search_box.schemas import SearchResultResponse
from app.control.websites.models import Website
from app.extractor.repo import save_provider_minimums
from app.infra.db import Base
from app.orchestration.results import aggregate_search_result, get_provider_airline_prices


class StoredSearchPriceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(
            self.engine,
            tables=[
                Website.__table__,
                Airport.__table__,
                SearchRequest.__table__,
                Airline.__table__,
                SearchProviderResult.__table__,
                SearchAirlinePrice.__table__,
                SearchLowestPrice.__table__,
            ],
        )
        with Session(self.engine) as db:
            db.add_all(
                [
                    Website(id=1, name="فروشنده یک"),
                    Website(id=2, name="فروشنده دو"),
                    Airport(id=1, name_fa="تهران", category="domestic"),
                    Airport(id=2, name_fa="مشهد", category="domestic"),
                    Airline(id=1, official_name_fa="ماهان"),
                    Airline(id=2, official_name_fa="زاگرس"),
                ]
            )
            db.flush()
            db.add(
                SearchRequest(
                    id=7,
                    route_type="domestic",
                    origin_airport_id=1,
                    destination_airport_id=2,
                    departure_date=date(2026, 9, 20),
                )
            )
            db.commit()

    @staticmethod
    def payload(website_id, source_job_id):
        return {
            "search_request_id": 7,
            "website_id": website_id,
            "route_type": "domestic",
            "snapshot_id": f"{source_job_id:032x}",
            "source_job_id": source_job_id,
        }

    def records(self):
        with Session(self.engine) as db:
            prices = [
                {
                    "search_request_id": row.search_request_id,
                    "website_id": row.website_id,
                    "airline": db.get(Airline, row.airline_id).official_name_fa,
                    "source_job_id": row.source_job_id,
                    "price": row.price,
                    "departure_time": row.departure_time,
                    "updated_at": row.updated_at.replace(tzinfo=timezone.utc),
                }
                for row in db.scalars(select(SearchLowestPrice))
            ]
            providers = [
                {
                    "search_request_id": row.search_request_id,
                    "website_id": row.website_id,
                    "source_job_id": row.source_job_id,
                    "offers_count": row.offers_count,
                    "updated_at": row.updated_at.replace(tzinfo=timezone.utc),
                }
                for row in db.scalars(select(SearchProviderResult))
            ]
        return prices, providers

    def provider_prices(self):
        with Session(self.engine) as db:
            return [
                (db.get(Airline, row.airline_id).official_name_fa, row.price)
                for row in db.scalars(
                    select(SearchAirlinePrice).order_by(
                        SearchAirlinePrice.website_id,
                        SearchAirlinePrice.airline_id,
                    )
                )
            ]

    def save(self, website_id, source_job_id, offers):
        with Session(self.engine) as db:
            return save_provider_minimums(
                db,
                self.payload(website_id, source_job_id),
                offers,
            )

    def test_persists_provider_minimum_then_aggregates_cross_provider_minimum(self):
        self.save(
            1,
            10,
            [
                {"airline": "ماهان", "price": 3_000_000, "time": "10:00"},
                {"airline": "ماهان", "price": 3_500_000, "time": "11:00"},
                {"airline": "زاگرس", "price": 2_000_000, "time": "12:00"},
                {"airline": "ناشناخته", "price": 1_000_000, "time": "13:00"},
            ],
        )
        self.save(
            2,
            11,
            [{"airline": "ماهان", "price": 2_500_000, "time": "14:00"}],
        )

        prices, providers = self.records()
        result = aggregate_search_result(
            7,
            prices,
            providers,
            [],
            {1: "فروشنده یک", 2: "فروشنده دو"},
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            [(offer["airline"], offer["price"], offer["website_id"]) for offer in result["offers"]],
            [("زاگرس", 2_000_000, 1), ("ماهان", 2_500_000, 2)],
        )
        self.assertEqual(
            self.provider_prices(),
            [("ماهان", 3_000_000), ("زاگرس", 2_000_000), ("ماهان", 2_500_000)],
        )
        self.assertIsNotNone(result["updated_at"])
        self.assertEqual(SearchResultResponse.model_validate(result).search_request_id, 7)

    def test_new_snapshot_replaces_old_prices_including_disappeared_airlines(self):
        self.save(
            1,
            10,
            [
                {"airline": "ماهان", "price": 2_000_000, "time": "10:00"},
                {"airline": "زاگرس", "price": 3_000_000, "time": "11:00"},
            ],
        )
        self.save(
            1,
            12,
            [{"airline": "ماهان", "price": 4_000_000, "time": "12:00"}],
        )
        prices, providers = self.records()
        self.assertEqual([(row["airline"], row["price"]) for row in prices], [("ماهان", 4_000_000)])
        self.assertEqual(providers[0]["source_job_id"], 12)

    def test_reads_each_airline_minimum_separately_for_every_provider(self):
        self.save(1, 10, [
            {"airline": "ماهان", "price": 3_000_000, "time": "10:00"},
            {"airline": "زاگرس", "price": 2_000_000, "time": "12:00"},
        ])
        self.save(2, 11, [
            {"airline": "ماهان", "price": 2_500_000, "time": "14:00"},
        ])
        with Session(self.engine) as db:
            offers = get_provider_airline_prices(db, 7)
        self.assertEqual(
            [(item["airline"], item["website_id"], item["price"]) for item in offers],
            [("زاگرس", 1, 2_000_000), ("ماهان", 1, 3_000_000), ("ماهان", 2, 2_500_000)],
        )

    def test_late_old_worker_cannot_overwrite_newer_persisted_result(self):
        self.save(1, 12, [{"airline": "ماهان", "price": 4_000_000, "time": "12:00"}])
        before_prices, before_providers = self.records()
        self.assertFalse(
            self.save(1, 10, [{"airline": "ماهان", "price": 1_000_000, "time": "08:00"}])
        )
        self.assertEqual(self.records(), (before_prices, before_providers))

    def test_empty_new_result_clears_stale_prices_and_updates_timestamp(self):
        self.save(1, 10, [{"airline": "ماهان", "price": 2_000_000, "time": "10:00"}])
        _, before = self.records()
        self.save(1, 11, [])
        prices, after = self.records()
        self.assertEqual(prices, [])
        self.assertEqual(after[0]["offers_count"], 0)
        self.assertEqual(after[0]["source_job_id"], 11)
        self.assertGreaterEqual(after[0]["updated_at"], before[0]["updated_at"] - timedelta(seconds=1))

    def test_failed_provider_does_not_hide_another_persisted_result(self):
        self.save(2, 11, [{"airline": "ماهان", "price": 2_500_000, "time": "14:00"}])
        prices, providers = self.records()
        failed_scrape = {
            "id": 12,
            "type": "scrape",
            "status": "failed",
            "outcome": "error",
            "payload": self.payload(1, 12),
        }
        result = aggregate_search_result(
            7,
            prices,
            providers,
            [failed_scrape],
            {1: "فروشنده خراب", 2: "فروشنده سالم"},
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["offers"][0]["price"], 2_500_000)
        self.assertEqual({row["status"] for row in result["providers"]}, {"failed", "ready"})


if __name__ == "__main__":
    unittest.main()
