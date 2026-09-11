"""Sample website-specific codes for shared airports."""

from sqlalchemy import or_, select

from app.control.airports.models import Airport
from app.control.flight_paths.models import FlightPath
from app.control.flight_paths.service import clean_code
from app.control.websites.models import Website
from app.infra.seeders.database import get_seed_session


FLIGHT_PATHS = [
    # علی‌بابا
    {
        "website_name": "علی‌بابا",
        "airport_name_fa": "تهران",
        "code": "THR",
    },
    {
        "website_name": "علی‌بابا",
        "airport_name_fa": "مشهد",
        "code": "MHD",
    },
    {
        "website_name": "علی‌بابا",
        "airport_name_fa": "استانبول",
        "code": "ISTALL",
    },

    # اسنپ‌تریپ
    {
        "website_name": "اسنپ‌تریپ",
        "airport_name_fa": "تهران",
        "code": "THR_city",
    },
    {
        "website_name": "اسنپ‌تریپ",
        "airport_name_fa": "مشهد",
        "code": "MHD_city",
    },
    {
        "website_name": "اسنپ‌تریپ",
        "airport_name_fa": "استانبول",
        "code": "IST_city",
    },
    {
        "website_name": "اسنپ‌تریپ",
        "airport_name_fa": "دبی",
        "code": "DXB_city",
    },

    # فلای‌تودی
    {
        "website_name": "فلای‌تودی",
        "airport_name_fa": "تهران",
        "code": "thr,1",
    },
    {
        "website_name": "فلای‌تودی",
        "airport_name_fa": "مشهد",
        "code": "mhd,1",
    },

    # مستربلیط
    {
        "website_name": "مستربلیط",
        "airport_name_fa": "تهران",
        "code": "THR",
    },
    {
        "website_name": "مستربلیط",
        "airport_name_fa": "مشهد",
        "code": "MHD",
    },
    {
        "website_name": "مستربلیط",
        "airport_name_fa": "استانبول",
        "code": "ISTALL",
    },

    # قاصدک ۲۴
    {
        "website_name": "قاصدک ۲۴",
        "airport_name_fa": "تهران",
        "code": "THR",
    },
    {
        "website_name": "قاصدک ۲۴",
        "airport_name_fa": "مشهد",
        "code": "MHD",
    },
    {
        "website_name": "قاصدک ۲۴",
        "airport_name_fa": "استانبول",
        "code": "ISTALL",
    },
    {
        "website_name": "قاصدک ۲۴",
        "airport_name_fa": "لندن",
        "code": "LONALL",
    },
]


def seed_flight_paths() -> None:
    db = get_seed_session()
    added = 0

    try:
        for item in FLIGHT_PATHS:
            website = db.scalar(
                select(Website).where(
                    Website.name
                    == item["website_name"]
                )
            )

            if website is None:
                raise ValueError(
                    f"Seed websites first: "
                    f"{item['website_name']} "
                    "does not exist."
                )

            airport = db.scalar(
                select(Airport).where(
                    Airport.name_fa == item["airport_name_fa"]
                )
            )

            if airport is None:
                raise ValueError(
                    f"Seed airports first: "
                    f"{item['airport_name_fa']} does not exist."
                )

            code = clean_code(item["code"])

            existing = db.scalar(
                select(FlightPath.id).where(
                    FlightPath.website_id == website.id,
                    or_(
                        FlightPath.airport_id == airport.id,
                        FlightPath.code == code,
                    ),
                )
            )

            if existing is not None:
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
            f"Flight path seeding completed. "
            f"Added {added} airport codes."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_flight_paths()