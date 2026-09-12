"""Minimal website-specific location codes verified for the initial seed."""

from sqlalchemy import or_, select

from app.control.airports.models import Airport
from app.control.flight_paths.models import FlightPath
from app.control.flight_paths.service import clean_code
from app.control.websites.models import Website
from app.infra.seeders.database import get_seed_session


FLIGHT_PATHS = [
    {"website_name": "علی‌بابا", "airport_name_fa": "تهران", "code": "THR"},
    {"website_name": "علی‌بابا", "airport_name_fa": "مشهد", "code": "MHD"},

    {"website_name": "اسنپ‌تریپ", "airport_name_fa": "تهران", "code": "THR_city"},
    {"website_name": "اسنپ‌تریپ", "airport_name_fa": "مشهد", "code": "MHD_city"},
    {"website_name": "اسنپ‌تریپ", "airport_name_fa": "استانبول", "code": "IST_city"},

    {"website_name": "فلای‌تودی", "airport_name_fa": "تهران", "code": "thr,1"},
    {"website_name": "فلای‌تودی", "airport_name_fa": "مشهد", "code": "mhd,1"},
    {"website_name": "فلای‌تودی", "airport_name_fa": "استانبول", "code": "ist,1"},

    {"website_name": "مستربلیط", "airport_name_fa": "تهران", "code": "THR"},
    {"website_name": "مستربلیط", "airport_name_fa": "مشهد", "code": "MHD"},
    {"website_name": "مستربلیط", "airport_name_fa": "استانبول", "code": "ISTALL"},

    {"website_name": "قاصدک ۲۴", "airport_name_fa": "تهران", "code": "THR"},
    {"website_name": "قاصدک ۲۴", "airport_name_fa": "مشهد", "code": "MHD"},
    {"website_name": "قاصدک ۲۴", "airport_name_fa": "استانبول", "code": "ISTALL"},
]


def seed_flight_paths() -> None:
    db = get_seed_session()
    added = 0
    updated = 0

    try:
        for item in FLIGHT_PATHS:
            website = db.scalar(
                select(Website).where(
                    Website.name == item["website_name"]
                )
            )

            if website is None:
                raise ValueError(
                    f"Seed websites first: {item['website_name']} does not exist."
                )

            airport = db.scalar(
                select(Airport).where(
                    Airport.name_fa == item["airport_name_fa"]
                )
            )

            if airport is None:
                raise ValueError(
                    f"Seed airports first: {item['airport_name_fa']} does not exist."
                )

            code = clean_code(item["code"])

            by_airport = db.scalar(
                select(FlightPath).where(
                    FlightPath.website_id == website.id,
                    FlightPath.airport_id == airport.id,
                )
            )

            if by_airport is not None:
                if by_airport.code != code:
                    code_owner = db.scalar(
                        select(FlightPath.id).where(
                            FlightPath.website_id == website.id,
                            FlightPath.code == code,
                            FlightPath.id != by_airport.id,
                        )
                    )
                    if code_owner is not None:
                        raise ValueError(
                            f"Duplicate code {code!r} for website {website.name}."
                        )
                    by_airport.code = code
                    updated += 1
                continue

            existing_code = db.scalar(
                select(FlightPath.id).where(
                    FlightPath.website_id == website.id,
                    FlightPath.code == code,
                )
            )

            if existing_code is not None:
                continue

            db.add(
                FlightPath(
                    website_id=website.id,
                    airport_id=airport.id,
                    code=code,
                )
            )
            db.flush()
            added += 1

        db.commit()

        print(
            "Flight path seeding completed. "
            f"Added {added}, updated {updated}."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_flight_paths()
