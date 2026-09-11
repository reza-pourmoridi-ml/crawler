import json
import logging
import signal
import threading

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.control.search_box.models import SearchRequest
from app.control.flight_paths.models import FlightPath  # noqa: F401

from app.infra.db import SessionLocal
from app.orchestration.jobs import advance_pipeline, create_scrape_jobs



POLL_INTERVAL_SECONDS = 5 * 60

def get_search_requests() -> list[dict]:
    """
    Search Requestهای ثبت‌شده توسط Search Box را می‌خواند.
    """

    statement = (
        select(SearchRequest)
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

                "departure_date":
                    item.departure_date.isoformat(),

                "departure_date_jalali":
                    item.departure_date_jalali,

                "created_at":
                    item.created_at.isoformat(),
            }
            for item in requests
        ]


def check_search_requests() -> list[dict]:
    requests = get_search_requests()

    print(
        "\n[orchestrator] search requests:",
        flush=True,
    )

    print(
        json.dumps(
            requests,
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    create_scrape_jobs(requests)
    advance_pipeline()

    return requests


def run() -> None:
    logging.basicConfig(level=logging.INFO)
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

    print(
        (
            "[orchestrator] started; "
            "checking search requests "
            "every 5 minutes."
        ),
        flush=True,
    )

    while not stop_event.is_set():

        try:
            check_search_requests()
        except Exception:
            logging.exception("[orchestrator] Pipeline check failed; will retry next poll")

        stop_event.wait(
            POLL_INTERVAL_SECONDS
        )

    print(
        "[orchestrator] stopped.",
        flush=True,
    )


if __name__ == "__main__":
    run()
