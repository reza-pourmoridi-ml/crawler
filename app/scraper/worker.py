import asyncio
import logging
from datetime import date
from pathlib import Path

from app.control.search_box.models import SearchRequest
from app.infra.db import SessionLocal
from app.infra.config import settings
from app.infra.worker_base import run_worker
from app.infra.storage import snapshot_directory
from app.scraper.service import scrape_url
from app.scraper.url_builder import build_scrape_url


logger = logging.getLogger(__name__)

JOB_TYPE = "scrape"
JOB_TIMEOUT = settings.scrape_job_timeout
OUTPUT_ROOT = Path("scraper_raw_data")


def handle_scrape(payload: dict) -> None:
    search_request_id = int(
        payload["search_request_id"]
    )

    website_id = int(
        payload["website_id"]
    )

    headless = payload.get(
        "headless",
        True,
    )

    with SessionLocal() as db:
        search_request = db.get(
            SearchRequest,
            search_request_id,
        )

        if search_request is None:
            raise ValueError(
                f"Search request {search_request_id} not found."
            )

        url = build_scrape_url(
            db,
            website_id=website_id,
            route_type=payload.get("route_type", search_request.route_type),
            origin_airport_id=payload.get("origin_airport_id", search_request.origin_airport_id),
            destination_airport_id=payload.get("destination_airport_id", search_request.destination_airport_id),
            departure_date=(date.fromisoformat(payload["departure_date"])
                            if "departure_date" in payload else search_request.departure_date),
        )

    if payload.get("snapshot_id"):
        output_dir = snapshot_directory(payload)
    else:
        output_dir = OUTPUT_ROOT / f"request_{search_request_id}" / f"website_{website_id}"

    result = asyncio.run(
        scrape_url(
            url,
            output_dir=output_dir,
            headless_mode=headless,
        )
    )

    if result.get("status") != "success":
        raise RuntimeError(
            f"Scrape failed with status={result.get('status')}"
        )

    logger.info(
        "Scrape completed search_request=%s website=%s url=%s result=%s",
        search_request_id,
        website_id,
        url,
        result,
    )


HANDLERS = {
    JOB_TYPE: handle_scrape,
}


TIMEOUTS = {
    JOB_TYPE: JOB_TIMEOUT,
}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO
    )

    run_worker(
        job_types=list(HANDLERS),
        handlers=HANDLERS,
        timeouts=TIMEOUTS,
        isolate_handlers=True,
    )


if __name__ == "__main__":
    main()
