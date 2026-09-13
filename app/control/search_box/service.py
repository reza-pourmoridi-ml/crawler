from datetime import date

from sqlalchemy.orm import Session

from app.control.airports.models import (
    Airport,
)

from app.control.search_box import repo

from app.control.search_box.jalali import (
    parse_jalali_date,
)

from app.control.search_box.models import (
    SearchRequest,
)


ROUTE_TYPES = {
    "domestic",
    "international",
}


class SearchAirportNotFoundError(
    ValueError
):
    pass


def clean_route_type(
    value: str,
) -> str:

    value = (
        value
        .strip()
        .lower()
    )

    if value not in ROUTE_TYPES:

        raise ValueError(
            "نوع مسیر باید "
            "داخلی یا خارجی باشد."
        )

    return value


def get_page_data(
    db: Session,
) -> tuple[
    list[Airport],
    list[SearchRequest],
    list[SearchRequest],
]:

    airports = (
        repo.get_all_airports(
            db
        )
    )

    requests = (
        repo.get_all_search_requests(
            db
        )
    )

    domestic_requests = [
        item
        for item in requests
        if (
            item.route_type
            ==
            "domestic"
        )
    ]

    international_requests = [
        item
        for item in requests
        if (
            item.route_type
            ==
            "international"
        )
    ]

    return (
        airports,
        domestic_requests,
        international_requests,
    )


def get_search_requests(
    db: Session,
) -> list[SearchRequest]:

    return (
        repo.get_all_search_requests(
            db
        )
    )


def get_search_request(
    db: Session,
    search_request_id: int,
) -> SearchRequest | None:
    return repo.get_search_request(db, search_request_id)


def require_airport(
    db: Session,
    airport_id: int,
) -> Airport:

    if airport_id <= 0:

        raise ValueError(
            "یک فرودگاه معتبر "
            "انتخاب کنید."
        )

    airport = repo.get_airport(
        db,
        airport_id,
    )

    if airport is None:

        raise SearchAirportNotFoundError(
            "فرودگاه انتخاب‌شده "
            "وجود ندارد."
        )

    return airport


def _validate_airport_category(
    airport: Airport,
    route_type: str,
    label: str,
) -> None:

    if (
        airport.category
        ==
        route_type
    ):
        return

    route_label = (
        "داخلی"
        if route_type == "domestic"
        else "خارجی"
    )

    raise ValueError(
        f"{label} باید از "
        f"فرودگاه‌های {route_label} "
        "انتخاب شود."
    )


def create_search_request(
    db: Session,

    route_type: str,

    origin_airport_id: int,

    destination_airport_id: int,

    departure_date_jalali: str,
) -> SearchRequest:

    route_type = clean_route_type(
        route_type
    )

    origin = require_airport(
        db,
        origin_airport_id,
    )

    destination = require_airport(
        db,
        destination_airport_id,
    )

    if (
        origin.id
        ==
        destination.id
    ):

        raise ValueError(
            "مبدأ و مقصد نمی‌توانند "
            "یکسان باشند."
        )

    _validate_airport_category(
        origin,
        route_type,
        "مبدأ",
    )

    _validate_airport_category(
        destination,
        route_type,
        "مقصد",
    )

    # ورودی کاربر:
    # 1405-06-20
    #
    # مقدار DB:
    # 2026-09-11
    departure_date: date = (
        parse_jalali_date(
            departure_date_jalali
        )
    )

    search_request = SearchRequest(
        route_type=
            route_type,

        origin_airport_id=
            origin.id,

        destination_airport_id=
            destination.id,

        departure_date=
            departure_date,
    )

    db.add(
        search_request
    )

    db.commit()

    db.refresh(
        search_request
    )

    return search_request
