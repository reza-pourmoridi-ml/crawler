"""Website configurations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.control.websites.models import Website

from app.control.websites.schemas import (
    clean_date_calendar,
    clean_date_format,
    clean_url_format,
    clean_website_name,
)

from app.infra.seeders.database import (
    get_seed_session,
)


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
]


def seed_websites(
    db: Session | None = None,
) -> None:

    owns_session = db is None

    if db is None:
        db = get_seed_session()

    created = 0
    updated = 0

    try:

        for item in WEBSITES:

            name = clean_website_name(
                item["name"]
            )

            values = {
                "domestic_url_format":
                    clean_url_format(
                        item[
                            "domestic_url_format"
                        ],
                        "فرمت URL داخلی",
                    ),

                "international_url_format":
                    clean_url_format(
                        item[
                            "international_url_format"
                        ],
                        "فرمت URL خارجی",
                    ),

                "date_calendar":
                    clean_date_calendar(
                        item["date_calendar"]
                    ),

                "date_format":
                    clean_date_format(
                        item["date_format"]
                    ),
            }

            website = db.scalar(
                select(Website).where(
                    Website.name == name
                )
            )

            if website is None:

                db.add(
                    Website(
                        name=name,
                        **values,
                    )
                )

                db.flush()

                created += 1

                continue

            changed = False

            for field, value in values.items():

                if getattr(
                    website,
                    field,
                ) != value:

                    setattr(
                        website,
                        field,
                        value,
                    )

                    changed = True

            if changed:
                updated += 1

        db.commit()

        print(
            "Website seeding completed. "
            f"Created {created}, "
            f"updated {updated}."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    seed_websites()