import unicodedata

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.control import repo
from app.control.airlines.models import Airline, AirlineAlias


class AirlineNotFoundError(Exception):
    pass


class AirlineAlreadyExistsError(Exception):
    pass


def get_airlines(db: Session) -> list[Airline]:
    return repo.get_all_airlines(db)


def get_airline(
    db: Session,
    airline_id: int,
) -> Airline:
    airline = repo.get_airline(
        db=db,
        airline_id=airline_id,
    )

    if airline is None:
        raise AirlineNotFoundError(
            f"Airline {airline_id} not found."
        )

    return airline


def _clean_airline_values(
    official_name_fa: str,
    aliases: list[str],
) -> tuple[str, list[str]]:
    official_name_fa = official_name_fa.strip()

    if not official_name_fa:
        raise ValueError(
            "نام رسمی فارسی نمی‌تواند خالی باشد."
        )

    if len(official_name_fa) > 255:
        raise ValueError(
            "نام رسمی فارسی نمی‌تواند بیشتر از ۲۵۵ نویسه باشد."
        )
    if any(unicodedata.category(char) == "Cc" for char in official_name_fa):
        raise ValueError("نام رسمی فارسی دارای نویسهٔ نامعتبر است.")

    # حذف فاصله‌های اضافی و aliasهای خالی
    cleaned_aliases = []
    seen = set()

    for alias in aliases:
        alias = alias.strip()

        if not alias:
            continue

        if len(alias) > 255:
            raise ValueError(
                "نام مستعار نمی‌تواند بیشتر از ۲۵۵ نویسه باشد."
            )
        if any(unicodedata.category(char) == "Cc" for char in alias):
            raise ValueError("نام مستعار دارای نویسهٔ نامعتبر است.")

        if alias in seen:
            continue

        seen.add(alias)
        cleaned_aliases.append(alias)

    return official_name_fa, cleaned_aliases


def _save_airline(db: Session, airline: Airline) -> Airline:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AirlineAlreadyExistsError(
            "An airline with this name already exists."
        )

    db.refresh(airline)
    return airline


def create_airline(
    db: Session,
    official_name_fa: str,
    aliases: list[str],
) -> Airline:
    official_name_fa, cleaned_aliases = _clean_airline_values(
        official_name_fa, aliases
    )
    airline = Airline(
        official_name_fa=official_name_fa,
        aliases=[AirlineAlias(alias_name=alias) for alias in cleaned_aliases],
    )
    db.add(airline)
    return _save_airline(db, airline)


def update_airline(
    db: Session,
    airline_id: int,
    official_name_fa: str,
    aliases: list[str],
) -> Airline:
    airline = get_airline(db=db, airline_id=airline_id)
    official_name_fa, cleaned_aliases = _clean_airline_values(
        official_name_fa, aliases
    )
    airline.official_name_fa = official_name_fa

    # حفظ Aliasهای موجود برای جلوگیری از تداخل با قید یکتایی هنگام ذخیره
    existing_aliases = {
        alias.alias_name: alias
        for alias in airline.aliases
    }
    airline.aliases = [
        existing_aliases[alias_name]
        if alias_name in existing_aliases
        else AirlineAlias(alias_name=alias_name)
        for alias_name in cleaned_aliases
    ]

    return _save_airline(db, airline)


def delete_airline(db: Session, airline_id: int) -> None:
    airline = get_airline(db=db, airline_id=airline_id)
    db.delete(airline)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
