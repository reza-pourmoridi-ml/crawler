from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.control.websites import repo

from app.control.websites.models import (
    Website,
)

from app.control.websites.schemas import (
    clean_date_calendar,
    clean_date_format,
    clean_url_format,
    clean_website_name,
)


class WebsiteNotFoundError(Exception):
    pass


class WebsiteAlreadyExistsError(Exception):
    pass


class WebsiteInUseError(Exception):
    pass


DUPLICATE_MESSAGE = (
    "وب‌سایتی با این نام از قبل وجود دارد."
)

IN_USE_MESSAGE = (
    "این وب‌سایت کد فرودگاه ثبت‌شده دارد؛ "
    "ابتدا کدهای ستون این وب‌سایت را "
    "در صفحات فرودگاه‌ها خالی و ذخیره کنید."
)


def get_websites(
    db: Session,
) -> list[Website]:

    return repo.get_all_websites(
        db
    )


def get_website(
    db: Session,
    website_id: int,
) -> Website:

    website = repo.get_website(
        db,
        website_id,
    )

    if website is None:
        raise WebsiteNotFoundError(
            "وب‌سایت پیدا نشد."
        )

    return website


def _save(
    db: Session,
    website: Website,
) -> Website:

    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise WebsiteAlreadyExistsError(
            DUPLICATE_MESSAGE
        ) from exc

    db.refresh(
        website
    )

    return website


def _clean_fields(
    name: str,
    domestic_url_format: str,
    international_url_format: str,
    date_calendar: str,
    date_format: str,
) -> dict:

    return {
        "name":
            clean_website_name(name),

        "domestic_url_format":
            clean_url_format(
                domestic_url_format,
                "فرمت URL داخلی",
            ),

        "international_url_format":
            clean_url_format(
                international_url_format,
                "فرمت URL خارجی",
            ),

        "date_calendar":
            clean_date_calendar(
                date_calendar
            ),

        "date_format":
            clean_date_format(
                date_format
            ),
    }


def create_website(
    db: Session,
    name: str,
    domestic_url_format: str,
    international_url_format: str,
    date_calendar: str,
    date_format: str,
) -> Website:

    website = Website(
        **_clean_fields(
            name,
            domestic_url_format,
            international_url_format,
            date_calendar,
            date_format,
        )
    )

    db.add(
        website
    )

    return _save(
        db,
        website,
    )


def update_website(
    db: Session,
    website_id: int,
    name: str,
    domestic_url_format: str,
    international_url_format: str,
    date_calendar: str,
    date_format: str,
) -> Website:

    website = get_website(
        db,
        website_id,
    )

    values = _clean_fields(
        name,
        domestic_url_format,
        international_url_format,
        date_calendar,
        date_format,
    )

    for field, value in values.items():
        setattr(
            website,
            field,
            value,
        )

    return _save(
        db,
        website,
    )


def delete_website(
    db: Session,
    website_id: int,
) -> None:

    website = get_website(
        db,
        website_id,
    )

    db.delete(
        website
    )

    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise WebsiteInUseError(
            IN_USE_MESSAGE
        ) from exc