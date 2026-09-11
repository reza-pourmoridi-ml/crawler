from datetime import date

from sqlalchemy.orm import Session

from app.control.flight_paths import repo as flight_path_repo
from app.control.search_box.jalali import gregorian_to_jalali
from app.control.websites import service as website_service


class ScrapeUrlBuildError(ValueError):
    pass


def format_date_for_website(
    value: date,
    calendar: str,
    date_format: str,
) -> str:
    if calendar == "jalali":
        year, month, day = gregorian_to_jalali(
            value
        )

    elif calendar == "gregorian":
        year = value.year
        month = value.month
        day = value.day

    else:
        raise ScrapeUrlBuildError(
            f"Unsupported calendar: {calendar}"
        )

    return (
        date_format
        .replace(
            "YYYY",
            f"{year:04d}",
        )
        .replace(
            "MM",
            f"{month:02d}",
        )
        .replace(
            "DD",
            f"{day:02d}",
        )
    )


def get_flight_path_code(
    db: Session,
    website_id: int,
    airport_id: int,
) -> str:
    flight_path = (
        flight_path_repo
        .get_flight_path_by_airport_and_website(
            db,
            airport_id=airport_id,
            website_id=website_id,
        )
    )

    if flight_path is None:
        raise ScrapeUrlBuildError(
            f"No flight path for airport={airport_id}, "
            f"website={website_id}"
        )

    return flight_path.code


def build_scrape_url(
    db: Session,
    website_id: int,
    route_type: str,
    origin_airport_id: int,
    destination_airport_id: int,
    departure_date: date,
) -> str:
    website = website_service.get_website(
        db,
        website_id,
    )

    if route_type == "domestic":
        url_template = (
            website.domestic_url_format
        )

    elif route_type == "international":
        url_template = (
            website.international_url_format
        )

    else:
        raise ScrapeUrlBuildError(
            f"Unsupported route type: {route_type}"
        )

    if not url_template:
        raise ScrapeUrlBuildError(
            f"Website {website_id} has no URL template for {route_type}"
        )

    if (
        not website.date_calendar
        or not website.date_format
    ):
        raise ScrapeUrlBuildError(
            f"Website {website_id} has incomplete date configuration"
        )

    origin_path = get_flight_path_code(
        db,
        website_id=website_id,
        airport_id=origin_airport_id,
    )

    destination_path = get_flight_path_code(
        db,
        website_id=website_id,
        airport_id=destination_airport_id,
    )

    formatted_date = format_date_for_website(
        departure_date,
        calendar=website.date_calendar,
        date_format=website.date_format,
    )

    return url_template.format(
        origin_path=origin_path,
        destination_path=destination_path,
        date=formatted_date,
    )