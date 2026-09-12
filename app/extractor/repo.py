from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.control.airlines.models import Airline
from app.control.flight_paths.models import FlightPath  # noqa: F401 - registers Airport relationship
from app.control.search_box.models import (
    SearchAirlinePrice,
    SearchLowestPrice,
    SearchProviderResult,
    SearchRequest,
)


def get_airlines(db) -> dict[str, list[str]]:
    """The notebook's {official name: [aliases]} format, loaded for each job."""
    airlines = db.scalars(select(Airline).options(selectinload(Airline.aliases)).order_by(Airline.id))
    return {
        airline.official_name_fa: list(dict.fromkeys([
            airline.official_name_fa,
            *(alias.alias_name for alias in sorted(airline.aliases, key=lambda alias: alias.id)),
        ]))
        for airline in airlines
    }


def save_provider_minimums(db, payload: dict, offers: list[dict]) -> bool:
    """Atomically replace one provider's prices unless a newer snapshot won the race."""
    search_request_id = int(payload["search_request_id"])
    website_id = int(payload["website_id"])
    source_job_id = int(payload["source_job_id"])

    try:
        request_id = db.scalar(
            select(SearchRequest.id)
            .where(SearchRequest.id == search_request_id)
            .with_for_update()
        )
        if request_id is None:
            raise ValueError(f"Search request {search_request_id} not found.")

        provider_result = db.get(
            SearchProviderResult,
            (search_request_id, website_id),
        )
        if provider_result is not None and provider_result.source_job_id >= source_job_id:
            db.rollback()
            return False

        airline_ids = dict(
            db.execute(select(Airline.official_name_fa, Airline.id)).all()
        )
        minimums = {}
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            airline_id = airline_ids.get(offer.get("airline"))
            price = offer.get("price")
            if (
                airline_id is None
                or isinstance(price, bool)
                or not isinstance(price, int)
                or price <= 0
            ):
                continue
            current = minimums.get(airline_id)
            if current is None or price < current["price"]:
                minimums[airline_id] = {
                    "price": price,
                    "departure_time": (
                        offer.get("time")
                        if isinstance(offer.get("time"), str)
                        else ""
                    ),
                }

        updated_at = datetime.now(timezone.utc)
        db.execute(
            delete(SearchAirlinePrice).where(
                SearchAirlinePrice.search_request_id == search_request_id,
                SearchAirlinePrice.website_id == website_id,
            )
        )
        db.add_all(
            [
                SearchAirlinePrice(
                    search_request_id=search_request_id,
                    website_id=website_id,
                    airline_id=airline_id,
                    source_job_id=source_job_id,
                    price=minimum["price"],
                    departure_time=minimum["departure_time"],
                    updated_at=updated_at,
                )
                for airline_id, minimum in minimums.items()
            ]
        )

        if provider_result is None:
            provider_result = SearchProviderResult(
                search_request_id=search_request_id,
                website_id=website_id,
                source_job_id=source_job_id,
                offers_count=len(minimums),
                updated_at=updated_at,
            )
            db.add(provider_result)
        else:
            provider_result.source_job_id = source_job_id
            provider_result.offers_count = len(minimums)
            provider_result.updated_at = updated_at

        db.flush()
        provider_prices = list(
            db.scalars(
                select(SearchAirlinePrice)
                .where(SearchAirlinePrice.search_request_id == search_request_id)
                .order_by(
                    SearchAirlinePrice.price,
                    SearchAirlinePrice.website_id,
                    SearchAirlinePrice.source_job_id.desc(),
                )
            )
        )
        lowest_by_airline = {}
        for provider_price in provider_prices:
            lowest_by_airline.setdefault(provider_price.airline_id, provider_price)

        db.execute(
            delete(SearchLowestPrice).where(
                SearchLowestPrice.search_request_id == search_request_id
            )
        )
        db.add_all(
            [
                SearchLowestPrice(
                    search_request_id=search_request_id,
                    airline_id=airline_id,
                    website_id=provider_price.website_id,
                    source_job_id=provider_price.source_job_id,
                    price=provider_price.price,
                    departure_time=provider_price.departure_time,
                    updated_at=provider_price.updated_at,
                )
                for airline_id, provider_price in lowest_by_airline.items()
            ]
        )

        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
