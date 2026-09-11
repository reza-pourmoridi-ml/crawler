from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.control.airlines.models import Airline


def get_all_airlines(db: Session) -> list[Airline]:
    statement = (
        select(Airline)
        .options(selectinload(Airline.aliases))
        .order_by(Airline.official_name_fa)
    )

    return list(db.scalars(statement).unique().all())


def get_airline(
    db: Session,
    airline_id: int,
) -> Airline | None:
    statement = (
        select(Airline)
        .options(selectinload(Airline.aliases))
        .where(Airline.id == airline_id)
    )

    return db.scalars(statement).unique().first()