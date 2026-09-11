import unicodedata

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.control.airports.models import Airport
from app.control.flight_paths import repo
from app.control.flight_paths.models import FlightPath
from app.control.websites.models import Website


class FlightPathNotFoundError(Exception):
    pass


class FlightPathAlreadyExistsError(Exception):
    pass


class FlightPathWebsiteNotFoundError(ValueError):
    pass


class FlightPathAirportNotFoundError(ValueError):
    pass


DUPLICATE_MESSAGE = (
    "این کد قبلاً برای این وب‌سایت استفاده شده است "
    "یا برای این فرودگاه در این وب‌سایت قبلاً کدی ثبت شده است."
)


def clean_code(value: str) -> str:
    if any(
        unicodedata.category(char) == "Cc"
        for char in value
    ):
        raise ValueError(
            "کد فرودگاه دارای نویسهٔ نامعتبر است."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            "کد فرودگاه نمی‌تواند خالی باشد."
        )

    if len(value) > 255:
        raise ValueError(
            "کد فرودگاه نمی‌تواند بیشتر از ۲۵۵ نویسه باشد."
        )

    if any(char.isspace() for char in value):
        raise ValueError(
            "کد فرودگاه نباید فاصله داشته باشد."
        )

    return value


def require_website(
    db: Session,
    website_id: int,
) -> Website:
    if website_id <= 0:
        raise ValueError(
            "یک وب‌سایت معتبر انتخاب کنید."
        )

    website = db.get(
        Website,
        website_id,
    )

    if website is None:
        raise FlightPathWebsiteNotFoundError(
            "وب‌سایت انتخاب‌شده وجود ندارد."
        )

    return website


def require_airport(
    db: Session,
    airport_id: int,
) -> Airport:
    if airport_id <= 0:
        raise ValueError(
            "یک فرودگاه معتبر انتخاب کنید."
        )

    airport = repo.get_airport(
        db,
        airport_id,
    )

    if airport is None:
        raise FlightPathAirportNotFoundError(
            "فرودگاه انتخاب‌شده وجود ندارد."
        )

    return airport


def get_airport_matrix(
    db: Session,
    category: str,
):
    websites = repo.get_all_websites(db)

    airports = repo.get_airports_by_category(
        db,
        category,
    )

    paths = repo.get_all_flight_paths(db)

    airport_ids = {
        airport.id
        for airport in airports
    }

    matrix: dict[int, dict[int, str]] = {
        airport.id: {}
        for airport in airports
    }

    for path in paths:
        if path.airport_id in airport_ids:
            matrix[path.airport_id][
                path.website_id
            ] = path.code

    return airports, websites, matrix


def get_flight_paths(
    db: Session,
    website_id: int | None = None,
) -> list[FlightPath]:
    if website_id is not None:
        require_website(
            db,
            website_id,
        )

    return repo.get_all_flight_paths(
        db,
        website_id,
    )


def get_flight_path(
    db: Session,
    flight_path_id: int,
) -> FlightPath:
    flight_path = repo.get_flight_path(
        db,
        flight_path_id,
    )

    if flight_path is None:
        raise FlightPathNotFoundError(
            "کد فرودگاه پیدا نشد."
        )

    return flight_path


def _commit(
    db: Session,
    duplicate_message: str = DUPLICATE_MESSAGE,
) -> None:
    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise FlightPathAlreadyExistsError(
            duplicate_message
        ) from exc


def create_flight_path(
    db: Session,
    website_id: int,
    airport_id: int,
    code: str,
) -> FlightPath:
    require_website(
        db,
        website_id,
    )

    require_airport(
        db,
        airport_id,
    )

    code = clean_code(code)

    flight_path = FlightPath(
        website_id=website_id,
        airport_id=airport_id,
        code=code,
    )

    db.add(flight_path)

    _commit(db)

    db.refresh(flight_path)

    return get_flight_path(
        db,
        flight_path.id,
    )


def update_flight_path(
    db: Session,
    flight_path_id: int,
    website_id: int,
    airport_id: int,
    code: str,
) -> FlightPath:
    flight_path = get_flight_path(
        db,
        flight_path_id,
    )

    require_website(
        db,
        website_id,
    )

    require_airport(
        db,
        airport_id,
    )

    code = clean_code(code)

    flight_path.website_id = website_id
    flight_path.airport_id = airport_id
    flight_path.code = code

    _commit(db)

    db.refresh(flight_path)

    return get_flight_path(
        db,
        flight_path.id,
    )


def set_airport_code(
    db: Session,
    airport_id: int,
    website_id: int,
    code: str,
) -> FlightPath | None:
    """
    Create/update one cell of the airport matrix.

    Empty value removes only the website-specific mapping.
    The airport itself is never deleted.
    """

    require_website(
        db,
        website_id,
    )

    require_airport(
        db,
        airport_id,
    )

    existing = (
        repo.get_flight_path_by_airport_and_website(
            db,
            airport_id=airport_id,
            website_id=website_id,
        )
    )

    stripped = code.strip()

    if not stripped:
        if existing is not None:
            db.delete(existing)
            db.commit()

        return None

    cleaned = clean_code(stripped)

    if existing is None:
        existing = FlightPath(
            airport_id=airport_id,
            website_id=website_id,
            code=cleaned,
        )

        db.add(existing)

    else:
        existing.code = cleaned

    _commit(
        db,
        (
            "این کد قبلاً برای فرودگاه دیگری "
            "در همین وب‌سایت استفاده شده است."
        ),
    )

    db.refresh(existing)

    return get_flight_path(
        db,
        existing.id,
    )


def delete_flight_path(
    db: Session,
    flight_path_id: int,
) -> None:
    db.delete(
        get_flight_path(
            db,
            flight_path_id,
        )
    )

    db.commit()