from sqlalchemy import select
from app.control.airlines.models import Airline, AirlineAlias
from app.infra.seeders.database import get_seed_session

AIRLINES = [
    {
        "official_name_fa": "ایران ایر",
        "aliases": [
            "ایران ایر",
            "ایران‌ایر",
            "هما",
            "هواپیمایی جمهوری اسلامی ایران",
            "Iran Air",
            "IRAN AIR",
            "IranAir",
            "Homa",
            "HOMA",
            "IR",
        ],
    },
    {
        "official_name_fa": "ماهان",
        "aliases": [
            "ماهان",
            "هواپیمایی ماهان",
            "ماهان ایر",
            "Mahan",
            "Mahan Air",
            "MAHAN AIR",
        ],
    },
    {
        "official_name_fa": "ایران ایرتور",
        "aliases": [
            "ایران ایرتور",
            "ایران‌ایرتور",
            "هواپیمایی ایران ایرتور",
            "Iran Airtour",
            "Iran Air Tour",
            "Iran Airtour Airlines",
        ],
    },
    {
        "official_name_fa": "آسمان",
        "aliases": [
            "آسمان",
            "هواپیمایی آسمان",
            "ایران آسمان",
            "Iran Aseman",
            "Iran Aseman Airlines",
            "Aseman",
            "Aseman Airlines",
        ],
    },
    {
        "official_name_fa": "کیش ایر",
        "aliases": [
            "کیش ایر",
            "کیش‌ایر",
            "هواپیمایی کیش",
            "Kish Air",
            "KishAir",
        ],
    },
    {
        "official_name_fa": "قشم ایر",
        "aliases": [
            "قشم ایر",
            "قشم‌ایر",
            "هواپیمایی قشم",
            "Qeshm Air",
            "QeshmAir",
        ],
    },
    {
        "official_name_fa": "زاگرس",
        "aliases": [
            "زاگرس",
            "هواپیمایی زاگرس",
            "زاگرس ایر",
            "Zagros",
            "Zagros Airlines",
        ],
    },
    {
        "official_name_fa": "کاسپین",
        "aliases": [
            "کاسپین",
            "هواپیمایی کاسپین",
            "کاسپین ایر",
            "Caspian",
            "Caspian Airlines",
        ],
    },
    {
        "official_name_fa": "تابان",
        "aliases": [
            "تابان",
            "هواپیمایی تابان",
            "تابان ایر",
            "Taban",
            "Taban Air",
            "Taban Airlines",
        ],
    },
    {
        "official_name_fa": "آتا",
        "aliases": [
            "آتا",
            "هواپیمایی آتا",
            "اتا",
            "ATA",
            "ATA Airlines",
        ],
    },
    {
        "official_name_fa": "وارش",
        "aliases": [
            "وارش",
            "هواپیمایی وارش",
            "وارش ایر",
            "Varesh",
            "Varesh Airlines",
        ],
    },
    {
        "official_name_fa": "سپهران",
        "aliases": [
            "سپهران",
            "هواپیمایی سپهران",
            "سپهران ایر",
            "Sepehran",
            "Sepehran Airlines",
        ],
    },
    {
        "official_name_fa": "معراج",
        "aliases": [
            "معراج",
            "هواپیمایی معراج",
            "معراج ایر",
            "Meraj",
            "Meraj Airlines",
        ],
    },
    {
        "official_name_fa": "کارون",
        "aliases": [
            "کارون",
            "هواپیمایی کارون",
            "کارون ایر",
            "Karun",
            "Karun Airlines",
        ],
    },
    {
        "official_name_fa": "پویا",
        "aliases": [
            "پویا",
            "هواپیمایی پویا",
            "پویا ایر",
            "Pouya",
            "Pouya Air",
        ],
    },
]


def seed_airlines() -> None:
    db = get_seed_session()

    try:
        for airline_data in AIRLINES:
            official_name = airline_data["official_name_fa"]

            airline = db.scalar(
                select(Airline).where(
                    Airline.official_name_fa == official_name
                )
            )

            if airline is None:
                airline = Airline(
                    official_name_fa=official_name,
                )

                db.add(airline)
                db.flush()

            existing_aliases = set(
                db.scalars(
                    select(AirlineAlias.alias_name).where(
                        AirlineAlias.airline_id == airline.id
                    )
                ).all()
            )

            for alias_name in airline_data["aliases"]:
                if alias_name not in existing_aliases:
                    db.add(
                        AirlineAlias(
                            airline_id=airline.id,
                            alias_name=alias_name,
                        )
                    )

        db.commit()

        print(
            f"Airline seeding completed successfully. "
            f"Processed {len(AIRLINES)} airlines."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_airlines()