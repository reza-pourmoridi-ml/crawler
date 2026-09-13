from sqlalchemy import select

from sqlalchemy.orm import (
    Session,
    joinedload,
)

from app.control.airports.models import Airport

from app.control.search_box.models import (
    SearchRequest,
)


def get_all_airports(
    db: Session,
) -> list[Airport]:

    statement = select(
        Airport
    ).order_by(
        Airport.category,
        Airport.name_fa,
        Airport.id,
    )

    return list(
        db.scalars(statement).all()
    )


def get_airport(
    db: Session,
    airport_id: int,
) -> Airport | None:

    return db.get(
        Airport,
        airport_id,
    )


def get_all_search_requests(
    db: Session,
) -> list[SearchRequest]:

    statement = (
        select(SearchRequest)
        .options(
            joinedload(
                SearchRequest.origin_airport
            ),
            joinedload(
                SearchRequest.destination_airport
            ),
        )
        .order_by(
            SearchRequest.created_at.desc(),
            SearchRequest.id.desc(),
        )
    )

    return list(
        db.scalars(statement).all()
    )


def get_search_request(
    db: Session,
    search_request_id: int,
) -> SearchRequest | None:
    statement = (
        select(SearchRequest)
        .options(
            joinedload(SearchRequest.origin_airport),
            joinedload(SearchRequest.destination_airport),
        )
        .where(SearchRequest.id == search_request_id)
    )
    return db.scalar(statement)
