"""Read persisted asynchronous provider prices and aggregate them per search."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.control.airlines.models import Airline
from app.control.search_box.models import (
    SearchAirlinePrice,
    SearchLowestPrice,
    SearchProviderResult,
    SearchRequest,
)
from app.control.websites.models import Website
from app.orchestration.models import Job


ACTIVE_STATUSES = {"pending", "running"}


class SearchResultNotFoundError(LookupError):
    pass


def job_succeeded(job: dict) -> bool:
    return job["status"] == "done" or (
        job["status"] == "failed" and job.get("outcome") == "success"
    )


def _provider_status(
    provider: dict | None,
    scrapes: list[dict],
    extractors: list[dict],
) -> str:
    if not scrapes:
        return "ready" if provider is not None else "waiting"

    latest_scrape = max(scrapes, key=lambda job: job["id"])
    persisted_source = provider["source_job_id"] if provider is not None else 0
    if latest_scrape["id"] <= persisted_source:
        return "ready"
    if latest_scrape["status"] in ACTIVE_STATUSES:
        return "updating" if provider is not None else "scraping"
    if not job_succeeded(latest_scrape):
        return "stale" if provider is not None else "failed"

    current_extractors = [
        job for job in extractors
        if job["payload"].get("source_job_id") == latest_scrape["id"]
    ]
    if not current_extractors:
        return "updating" if provider is not None else "processing"
    latest_extractor = max(current_extractors, key=lambda job: job["id"])
    if latest_extractor["status"] in ACTIVE_STATUSES or job_succeeded(latest_extractor):
        return "updating" if provider is not None else "processing"
    return "stale" if provider is not None else "failed"


def aggregate_search_result(
    search_request_id: int,
    prices: Iterable[dict],
    provider_results: Iterable[dict],
    jobs: Iterable[dict],
    website_names: dict[int, str],
) -> dict:
    """Choose the stored cross-provider minimum for every official airline."""
    prices = [row for row in prices if row["search_request_id"] == search_request_id]
    provider_results = [
        row for row in provider_results
        if row["search_request_id"] == search_request_id
    ]
    jobs = [
        job for job in jobs
        if job.get("payload", {}).get("search_request_id") == search_request_id
    ]
    scrapes = [job for job in jobs if job["type"] in {"scrape", "scrap"}]
    extractors = [job for job in jobs if job["type"] == "extractor"]
    providers_by_website = {row["website_id"]: row for row in provider_results}
    provider_ids = sorted(
        set(providers_by_website)
        | {
            int(job["payload"]["website_id"])
            for job in scrapes
            if job["payload"].get("website_id") is not None
        }
    )

    providers = []
    for website_id in provider_ids:
        provider = providers_by_website.get(website_id)
        providers.append(
            {
                "website_id": website_id,
                "website_name": website_names.get(website_id, f"وب‌سایت {website_id}"),
                "status": _provider_status(
                    provider,
                    [
                        job for job in scrapes
                        if int(job["payload"]["website_id"]) == website_id
                    ],
                    [
                        job for job in extractors
                        if int(job["payload"].get("website_id", -1)) == website_id
                    ],
                ),
                "offers_count": provider["offers_count"] if provider is not None else 0,
                "source_job_id": provider["source_job_id"] if provider is not None else None,
                "updated_at": provider["updated_at"] if provider is not None else None,
            }
        )

    minimums = {}
    for row in prices:
        candidate = {
            "airline": row["airline"],
            "price": row["price"],
            "time": row["departure_time"],
            "website_id": row["website_id"],
            "website_name": website_names.get(
                row["website_id"],
                f"وب‌سایت {row['website_id']}",
            ),
            "source_job_id": row["source_job_id"],
            "updated_at": row["updated_at"],
        }
        current = minimums.get(row["airline"])
        if current is None or (
            candidate["price"], candidate["website_id"], -candidate["source_job_id"]
        ) < (
            current["price"], current["website_id"], -current["source_job_id"]
        ):
            minimums[row["airline"]] = candidate

    offers = sorted(minimums.values(), key=lambda item: (item["price"], item["airline"]))
    statuses = {provider["status"] for provider in providers}
    if not providers:
        status = "waiting"
    elif statuses <= {"ready"}:
        status = "completed"
    elif offers:
        status = "partial"
    elif statuses <= {"failed"}:
        status = "failed"
    else:
        status = "processing"

    timestamps = [row["updated_at"] for row in provider_results]
    return {
        "search_request_id": search_request_id,
        "status": status,
        "updated_at": max(timestamps) if timestamps else None,
        "offers": offers,
        "providers": providers,
    }


def get_search_results(db: Session, search_request_ids: Iterable[int]) -> dict[int, dict]:
    ids = {int(request_id) for request_id in search_request_ids}
    if not ids:
        return {}

    website_names = dict(db.execute(select(Website.id, Website.name)).all())
    price_records = db.execute(
        select(SearchLowestPrice, Airline.official_name_fa)
        .join(Airline, Airline.id == SearchLowestPrice.airline_id)
        .where(SearchLowestPrice.search_request_id.in_(ids))
    ).all()
    prices = [
        {
            "search_request_id": price.search_request_id,
            "website_id": price.website_id,
            "airline": airline,
            "source_job_id": price.source_job_id,
            "price": price.price,
            "departure_time": price.departure_time,
            "updated_at": price.updated_at,
        }
        for price, airline in price_records
    ]
    provider_results = [
        {
            "search_request_id": row.search_request_id,
            "website_id": row.website_id,
            "source_job_id": row.source_job_id,
            "offers_count": row.offers_count,
            "updated_at": row.updated_at,
        }
        for row in db.scalars(
            select(SearchProviderResult).where(SearchProviderResult.search_request_id.in_(ids))
        )
    ]
    jobs = [
        {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "outcome": job.outcome,
            "payload": job.payload,
        }
        for job in db.scalars(
            select(Job)
            .where(Job.type.in_(["scrape", "scrap", "extractor"]))
            .order_by(Job.id)
        )
        if job.payload.get("search_request_id") in ids
    ]
    return {
        request_id: aggregate_search_result(
            request_id,
            prices,
            provider_results,
            jobs,
            website_names,
        )
        for request_id in ids
    }


def get_search_result(db: Session, search_request_id: int) -> dict:
    if db.get(SearchRequest, search_request_id) is None:
        raise SearchResultNotFoundError(f"Search request {search_request_id} not found.")
    return get_search_results(db, [search_request_id])[search_request_id]


def get_provider_airline_prices(db: Session, search_request_id: int) -> list[dict]:
    """Return each airline's persisted minimum separately for every provider."""
    rows = db.execute(
        select(SearchAirlinePrice, Airline.official_name_fa)
        .join(Airline, Airline.id == SearchAirlinePrice.airline_id)
        .where(SearchAirlinePrice.search_request_id == search_request_id)
        .order_by(Airline.official_name_fa, SearchAirlinePrice.website_id)
    ).all()
    return [
        {
            "airline": airline,
            "website_id": price.website_id,
            "price": price.price,
            "time": price.departure_time,
        }
        for price, airline in rows
    ]
