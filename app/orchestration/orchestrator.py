import logging
import signal
import threading

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.control.search_box.models import SearchRequest
from app.control.flight_paths.models import FlightPath  # noqa: F401

from app.infra.db import SessionLocal
from app.orchestration.jobs import advance_pipeline, create_scrape_jobs
from app.orchestration.maintenance import maintain_pipeline
from datetime import datetime
from zoneinfo import ZoneInfo
from app.infra.logging_config import configure_logging


POLL_INTERVAL_SECONDS = 5 * 60
logger = logging.getLogger(__name__)

def get_search_requests() -> list[dict]:
    today = datetime.now(
        ZoneInfo("Asia/Tehran")
    ).date()

    statement = (
        select(SearchRequest)
        .where(
            SearchRequest.departure_date >= today
        )
        .options(
            joinedload(
                SearchRequest.origin_airport
            ),
            joinedload(
                SearchRequest.destination_airport
            ),
        )
        .order_by(
            SearchRequest.created_at.asc(),
            SearchRequest.id.asc(),
        )
    )

    with SessionLocal() as db:
        requests = list(
            db.scalars(statement).all()
        )

        return [
            {
                "id": item.id,
                "route_type": item.route_type,
                "origin_airport": {
                    "id": item.origin_airport.id,
                    "name_fa": item.origin_airport.name_fa,
                },
                "destination_airport": {
                    "id": item.destination_airport.id,
                    "name_fa": item.destination_airport.name_fa,
                },
                "departure_date": item.departure_date.isoformat(),
                "departure_date_jalali": item.departure_date_jalali,
                "created_at": item.created_at.isoformat(),
            }
            for item in requests
        ]

def check_search_requests() -> list[dict]:
    requests = get_search_requests()

    # Do not log route/date payloads: they are user search data.
    logger.info("Scheduling eligible search requests count=%s", len(requests))

    create_scrape_jobs(requests)
    advance_pipeline()

    return requests


def run() -> None:
    configure_logging("orchestrator")
    stop_event = threading.Event()

    def stop(*_args) -> None:
        stop_event.set()

    signal.signal(
        signal.SIGTERM,
        stop,
    )

    signal.signal(
        signal.SIGINT,
        stop,
    )

    logger.info("Orchestrator started poll_interval_seconds=%s", POLL_INTERVAL_SECONDS)

    while not stop_event.is_set():

        try:
            maintain_pipeline()
        except Exception:
            logger.exception("Maintenance failed; will retry next poll")

        try:
            check_search_requests()
        except Exception:
            logger.exception("Pipeline check failed; will retry next poll")

        stop_event.wait(
            POLL_INTERVAL_SECONDS
        )

    logger.info("Orchestrator stopped")


if __name__ == "__main__":
    run()
