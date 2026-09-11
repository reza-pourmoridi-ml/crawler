from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.control.airlines.models import Airline


def get_airlines(db) -> dict[str, list[str]]:
    """The notebook's {official name: [aliases]} format, loaded for each job."""
    airlines = db.scalars(select(Airline).options(selectinload(Airline.aliases)).order_by(Airline.id))
    return {
        airline.official_name_fa: list(dict.fromkeys([
            airline.official_name_fa,
            *(alias.alias_name for alias in sorted(airline.aliases, key=lambda alias: alias.id)),
        ]))
        for airline in airlines
    }
