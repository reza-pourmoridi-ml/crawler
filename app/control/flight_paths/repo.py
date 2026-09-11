from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.control.airports.models import Airport
from app.control.flight_paths.models import FlightPath
from app.control.websites.models import Website


def get_all_websites(db: Session) -> list[Website]:
    return list(
        db.scalars(
            select(Website)
            .order_by(Website.name, Website.id)
        ).all()
    )


def get_airports_by_category(
    db: Session,
    category: str,
) -> list[Airport]:
    statement = (
        select(Airport)
        .where(Airport.category == category)
        .order_by(Airport.name_fa, Airport.id)
    )

    return list(db.scalars(statement).all())


def get_airport(
    db: Session,
    airport_id: int,
) -> Airport | None:
    return db.get(Airport, airport_id)


def get_all_flight_paths(
    db: Session,
    website_id: int | None = None,
) -> list[FlightPath]:
    statement = (
        select(FlightPath)
        .join(FlightPath.airport)
        .options(
            joinedload(FlightPath.website),
            joinedload(FlightPath.airport),
        )
    )

    if website_id is not None:
        statement = statement.where(
            FlightPath.website_id == website_id
        )

    statement = statement.order_by(
        Airport.name_fa,
        FlightPath.id,
    )

    return list(db.scalars(statement).all())


def get_flight_path(
    db: Session,
    flight_path_id: int,
) -> FlightPath | None:
    return db.scalar(
        select(FlightPath)
        .options(
            joinedload(FlightPath.website),
            joinedload(FlightPath.airport),
        )
        .where(
            FlightPath.id == flight_path_id
        )
    )


def get_flight_path_by_airport_and_website(
    db: Session,
    airport_id: int,
    website_id: int,
) -> FlightPath | None:
    return db.scalar(
        select(FlightPath)
        .options(
            joinedload(FlightPath.website),
            joinedload(FlightPath.airport),
        )
        .where(
            FlightPath.airport_id == airport_id,
            FlightPath.website_id == website_id,
        )
    )