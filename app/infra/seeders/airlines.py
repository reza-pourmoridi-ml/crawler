from sqlalchemy import select

from app.control.airlines.models import Airline, AirlineAlias
from app.infra.seeders.database import get_seed_session


AIRLINES = [
    {
        "official_name_fa": "ایران ایر",
        "aliases": [
            "ایران ایر",
            "هواپیمایی جمهوری اسلامی ایران",
            "هما",
            "Islamic Republic of Iran Airlines",
            "Homa",
            "Iran Air",
            "IranAir",
        ],
    },
    {
        "official_name_fa": "ماهان",
        "aliases": [
            "ماهان",
            "هواپیمایی ماهان",
            "ماهان ایر",
            "Mahan Air",
            "Mahan",
        ],
    },
    {
        "official_name_fa": "آسمان",
        "aliases": [
            "آسمان",
            "هواپیمایی آسمان",
            "ایران آسمان",
            "Aseman Airlines",
            "Iran Aseman Airlines",
            "Aseman",
        ],
    },
    {
        "official_name_fa": "آتا",
        "aliases": [
            "آتا",
            "هواپیمایی آتا",
            "آتا ایرلاین",
            "Ata Airlines",
            "Ata Airline",
            "Ata",
        ],
    },
    {
        "official_name_fa": "ایران ایرتور",
        "aliases": [
            "ایران ایرتور",
            "هواپیمایی ایران ایرتور",
            "هواپیمایی ایران ایرتور چارتر",
            "Iran Airtour Airline",
            "Iran Airtour",
            "Charter Airline",
            "Airtour",
        ],
    },
    {
        "official_name_fa": "کیش ایر",
        "aliases": [
            "کیش ایر",
            "هواپیمایی کیش ایر",
            "Kish Air",
            "Kish",
        ],
    },
    {
        "official_name_fa": "قشم ایر",
        "aliases": [
            "قشم ایر",
            "هواپیمایی قشم ایر",
            "Qeshm Air",
            "Qeshm",
        ],
    },
    {
        "official_name_fa": "کاسپین",
        "aliases": [
            "کاسپین",
            "هواپیمایی کاسپین",
            "کاسپین ایرلاین",
            "Caspian Airlines",
            "Caspian",
        ],
    },
    {
        "official_name_fa": "زاگرس",
        "aliases": [
            "زاگرس",
            "هواپیمایی زاگرس",
            "زاگرس ایرلاین",
            "Zagros Airlines",
            "Zagros",
        ],
    },
    {
        "official_name_fa": "زاگرس قشم",
        "aliases": [
            "زاگرس قشم",
            "هواپیمایی زاگرس قشم",
            "Zagros Qeshm",
        ],
    },
    {
        "official_name_fa": "تابان",
        "aliases": [
            "تابان",
            "هواپیمایی تابان",
            "تابان ایر",
            "Taban Air",
            "Taban",
        ],
    },
    {
        "official_name_fa": "سپهران",
        "aliases": [
            "سپهران",
            "هواپیمایی سپهران",
            "سپهران ایرلاین",
            "Sepehran Airlines",
            "Sepehran",
        ],
    },
    {
        "official_name_fa": "وارش",
        "aliases": [
            "وارش",
            "هواپیمایی وارش",
            "وارش ایرلاین",
            "Varesh Airlines",
            "Varesh",
        ],
    },
    {
        "official_name_fa": "کارون",
        "aliases": [
            "کارون",
            "هواپیمایی کارون",
            "کارون ایرلاین",
            "Karun Airlines",
            "Karun",
            "هواپیمایی نفت",
            "نفت ایر",
            "نفت",
            "Naft Air",
            "Naft",
        ],
    },
    {
        "official_name_fa": "چابهار",
        "aliases": [
            "چابهار",
            "هواپیمایی چابهار",
            "چابهار ایرلاین",
            "Chabahar Airlines",
            "Chabahar",
        ],
    },
    {
        "official_name_fa": "فلای پرشیا",
        "aliases": [
            "فلای پرشیا",
            "هواپیمایی فلای پرشیا",
            "Fly Persia",
            "FlyPersia",
        ],
    },
    {
        "official_name_fa": "آوا ایر",
        "aliases": [
            "آوا ایر",
            "هواپیمایی آوا ایر",
            "Ava Air",
            "Ava",
        ],
    },
    {
        "official_name_fa": "معراج",
        "aliases": [
            "معراج",
            "هواپیمایی معراج",
            "معراج ایر",
            "Meraj Airlines",
            "Meraj",
        ],
    },
    {
        "official_name_fa": "ساها",
        "aliases": [
            "ساها",
            "هواپیمایی ساها",
            "ساها ایر",
            "Saha Airlines",
            "Saha",
        ],
    },
    {
        "official_name_fa": "پویا",
        "aliases": [
            "پویا",
            "هواپیمایی پویا",
            "پویا ایر",
            "Pouya Air",
            "Pouya",
        ],
    },
    {
        "official_name_fa": "پارس ایر",
        "aliases": [
            "پارس ایر",
            "هواپیمایی پارس ایر",
            "Pars Air",
            "Pars",
        ],
    },
    {
        "official_name_fa": "یزد ایر",
        "aliases": [
            "یزد ایر",
            "هواپیمایی یزد ایر",
            "Yazd Air",
            "Yazd",
        ],
    },
    {
        "official_name_fa": "ایر وان",
        "aliases": [
            "ایر وان",
            "هواپیمایی ایر وان",
            "Air One",
            "AirOne",
        ],
    },
    {
        "official_name_fa": "آساجت",
        "aliases": [
            "آساجت",
            "هواپیمایی آساجت",
            "Asa Jet",
            "AsaJet",
        ],
    },
    {
        "official_name_fa": "رایمون",
        "aliases": [
            "رایمون",
            "هواپیمایی رایمون",
            "رایمون ایر",
            "Raymon Air",
            "Raymon",
        ],
    },
    {
        "official_name_fa": "مهر",
        "aliases": [
            "مهر",
            "هواپیمایی مهر",
            "مهر ایر",
            "Mehr Airlines",
            "Mehr",
        ],
    },
    {
        "official_name_fa": "اطلس",
        "aliases": [
            "اطلس",
            "هواپیمایی اطلس",
            "اطلس ایر",
            "Atlas Air",
            "Atlas",
        ],
    },
    {
        "official_name_fa": "فلای کیش",
        "aliases": [
            "فلای کیش",
            "هواپیمایی فلای کیش",
            "Fly Kish",
        ],
    },
    {
        "official_name_fa": "فجر",
        "aliases": [
            "فجر",
            "هواپیمایی فجر",
            "فجر ایر",
            "Fajr Air",
            "Fajr",
        ],
    },
    {
        "official_name_fa": "آریا",
        "aliases": [
            "آریا",
            "هواپیمایی آریا",
            "آریا ایر",
            "Aria Air",
            "Aria",
        ],
    },
    {
        "official_name_fa": "یاس",
        "aliases": [
            "یاس",
            "هواپیمایی یاس",
            "یاس ایر",
            "Yas Air",
            "Yas",
        ],
    },
    {
        "official_name_fa": "سورینت",
        "aliases": [
            "سورینت",
            "هواپیمایی سورینت",
            "سورینت ایر",
            "Surinet Air",
            "Surinet",
        ],
    },
    {
        "official_name_fa": "آرمان",
        "aliases": [
            "آرمان",
            "هواپیمایی آرمان",
            "آرمان ایر",
            "Arman Air",
            "Arman",
        ],
    },
    {
        "official_name_fa": "سیمرغ",
        "aliases": [
            "سیمرغ",
            "هواپیمایی سیمرغ",
            "سیمرغ ایر",
            "Simorgh Air",
            "Simorgh",
        ],
    },
    {
        "official_name_fa": "پارسیان",
        "aliases": [
            "پارسیان",
            "هواپیمایی پارسیان",
            "پارسیان ایر",
            "Parsian Air",
            "Parsian",
        ],
    },
    {
        "official_name_fa": "نسیم",
        "aliases": [
            "نسیم",
            "هواپیمایی نسیم",
            "خطوط هواپیمایی نسیم",
            "Nasim Airlines",
            "Nasim",
        ],
    },
    {
        "official_name_fa": "ایران ایر شارجه",
        "aliases": [
            "ایران ایر شارجه",
            "هواپیمایی ایران ایر شارجه",
            "CPN",
        ],
    },
    {
        "official_name_fa": "باری",
        "aliases": [
            "باری",
            "هواپیمایی باری",
            "Cargo Airline",
        ],
    },
    {
        "official_name_fa": "سروش",
        "aliases": [
            "سروش",
            "soroush",
        ],
    },
    {
        "official_name_fa": "اختصاصی/خصوصی",
        "aliases": [
            "اختصاصی",
            "خصوصی",
            "هواپیمایی اختصاصی",
            "هواپیمایی خصوصی",
            "Private Airline",
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
                    official_name_fa=official_name
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
                if alias_name in existing_aliases:
                    continue

                db.add(
                    AirlineAlias(
                        airline_id=airline.id,
                        alias_name=alias_name,
                    )
                )

                existing_aliases.add(alias_name)

        db.commit()

        print(
            "Airline seeding completed successfully. "
            f"Processed {len(AIRLINES)} airlines."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_airlines()