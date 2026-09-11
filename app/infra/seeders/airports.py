"""Shared airports. Category is relative to Iran, not to any website."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.control.airports.models import Airport
from app.infra.seeders.database import get_seed_session


AIRPORTS = [
    # داخلی
    {"name_fa": "تهران", "category": "domestic"},
    {"name_fa": "مشهد", "category": "domestic"},
    {"name_fa": "شیراز", "category": "domestic"},
    {"name_fa": "اصفهان", "category": "domestic"},
    {"name_fa": "تبریز", "category": "domestic"},
    {"name_fa": "اهواز", "category": "domestic"},
    {"name_fa": "کیش", "category": "domestic"},
    {"name_fa": "قشم", "category": "domestic"},
    {"name_fa": "بندرعباس", "category": "domestic"},
    {"name_fa": "کرمان", "category": "domestic"},
    {"name_fa": "رشت", "category": "domestic"},
    {"name_fa": "ساری", "category": "domestic"},
    {"name_fa": "یزد", "category": "domestic"},
    {"name_fa": "کرمانشاه", "category": "domestic"},
    {"name_fa": "ارومیه", "category": "domestic"},
    {"name_fa": "بوشهر", "category": "domestic"},
    {"name_fa": "چابهار", "category": "domestic"},

    # خارجی
    {"name_fa": "استانبول", "category": "international"},
    {"name_fa": "دبی", "category": "international"},
    {"name_fa": "لندن", "category": "international"},
]


def seed_airports(db: Session | None = None) -> None:
    owns_session = db is None

    if db is None:
        db = get_seed_session()

    created = 0
    reclassified = 0

    try:
        for item in AIRPORTS:
            airport = db.scalar(
                select(Airport).where(
                    Airport.name_fa == item["name_fa"]
                )
            )

            if airport is None:
                db.add(
                    Airport(
                        name_fa=item["name_fa"],
                        category=item["category"],
                    )
                )
                db.flush()
                created += 1

            elif airport.category != item["category"]:
                airport.category = item["category"]
                reclassified += 1

        db.commit()

        print(
            "Airport seeding completed. "
            f"Created {created}, reclassified {reclassified}."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    seed_airports()