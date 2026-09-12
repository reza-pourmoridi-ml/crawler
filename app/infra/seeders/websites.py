"""Initial website configurations verified against current public routes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.control.websites.models import Website
from app.control.websites.schemas import (
    clean_date_calendar,
    clean_date_format,
    clean_url_format,
    clean_website_name,
)
from app.infra.seeders.database import get_seed_session


WEBSITES = [
    {
        "name": "علی‌بابا",
        "domestic_url_format": (
            "https://www.alibaba.ir/flights/"
            "{origin_path}-{destination_path}"
            "?adult=1&child=0&infant=0"
            "&departing={date}"
        ),
        "international_url_format": (
            "https://www.alibaba.ir/international/"
            "{origin_path}-{destination_path}"
            "?adult=1&child=0&infant=0"
            "&departing={date}"
            "&flightClass=economy"
        ),
        "date_calendar": "jalali",
        "date_format": "YYYY-MM-DD",
    },
    {
        "name": "اسنپ‌تریپ",
        "domestic_url_format": (
            "https://www.snapptrip.com/flights/"
            "{origin_path}/{destination_path}"
            "?adultCount=1"
            "&cabinType=ECONOMY"
            "&childCount=0"
            "&dateType=jalali"
            "&departureDate={date}"
            "&infantCount=0"
        ),
        "international_url_format": (
            "https://www.snapptrip.com/inter-flights/"
            "{origin_path}/{destination_path}"
            "?adultCount=1"
            "&cabinType=ECONOMY"
            "&childCount=0"
            "&dateType=jalali"
            "&departureDate={date}"
            "&infantCount=0"
        ),
        "date_calendar": "gregorian",
        "date_format": "YYYY-MM-DD",
    },
    {
        "name": "فلای‌تودی",
        "domestic_url_format": (
            "https://www.flytoday.ir/flight/search"
            "?departure={origin_path}"
            "&arrival={destination_path}"
            "&departureDate={date}"
            "&adt=1&chd=0&inf=0"
            "&cabin=1"
            "&isAnyWhere=false"
        ),
        "international_url_format": (
            "https://www.flytoday.ir/flight/search"
            "?departure={origin_path}"
            "&arrival={destination_path}"
            "&departureDate={date}"
            "&adt=1&chd=0&inf=0"
            "&cabin=1"
            "&isAnyWhere=false"
        ),
        "date_calendar": "gregorian",
        "date_format": "YYYY-MM-DD",
    },
    {
        "name": "مستربلیط",
        "domestic_url_format": (
            "https://mrbilit.com/flights/"
            "{origin_path}-{destination_path}"
            "?adultCount=1"
            "&childCount=0"
            "&departureDate={date}"
            "&infantCount=0"
        ),
        "international_url_format": (
            "https://mrbilit.com/flights/"
            "{origin_path}-{destination_path}"
            "?adultCount=1"
            "&childCount=0"
            "&departureDate={date}"
            "&infantCount=0"
        ),
        "date_calendar": "jalali",
        "date_format": "YYYY-MM-DD",
    },
    {
        "name": "قاصدک ۲۴",
        "domestic_url_format": None,
        "international_url_format": None,
        "date_calendar": None,
        "date_format": None,
    },
]


def _clean_optional_url(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return clean_url_format(value, label)


def _clean_optional_calendar(value: str | None) -> str | None:
    if value is None:
        return None
    return clean_date_calendar(value)


def _clean_optional_date_format(value: str | None) -> str | None:
    if value is None:
        return None
    return clean_date_format(value)


def seed_websites(db: Session | None = None) -> None:
    owns_session = db is None

    if db is None:
        db = get_seed_session()

    created = 0
    updated = 0

    try:
        for item in WEBSITES:
            name = clean_website_name(item["name"])
            values = {
                "domestic_url_format": _clean_optional_url(
                    item["domestic_url_format"],
                    "فرمت URL داخلی",
                ),
                "international_url_format": _clean_optional_url(
                    item["international_url_format"],
                    "فرمت URL خارجی",
                ),
                "date_calendar": _clean_optional_calendar(
                    item["date_calendar"]
                ),
                "date_format": _clean_optional_date_format(
                    item["date_format"]
                ),
            }

            website = db.scalar(
                select(Website).where(Website.name == name)
            )

            if website is None:
                db.add(Website(name=name, **values))
                db.flush()
                created += 1
                continue

            changed = False

            for field, value in values.items():
                if getattr(website, field) != value:
                    setattr(website, field, value)
                    changed = True

            if changed:
                updated += 1

        db.commit()

        print(
            "Website seeding completed. "
            f"Created {created}, updated {updated}."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    seed_websites()
