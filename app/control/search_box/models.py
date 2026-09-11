from datetime import (
    date,
    datetime,
)

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    func,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.control.airports.models import (
    Airport,
)

from app.control.search_box.jalali import (
    format_jalali_date,
)

from app.infra.db import Base


class SearchRequest(Base):

    __tablename__ = (
        "search_requests"
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    route_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    origin_airport_id: Mapped[int] = (
        mapped_column(
            ForeignKey(
                "airports.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
            index=True,
        )
    )

    destination_airport_id: Mapped[int] = (
        mapped_column(
            ForeignKey(
                "airports.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
            index=True,
        )
    )

    departure_date: Mapped[date] = (
        mapped_column(
            Date,
            nullable=False,
            index=True,
        )
    )

    created_at: Mapped[datetime] = (
        mapped_column(
            DateTime(
                timezone=True
            ),
            server_default=func.now(),
            nullable=False,
        )
    )

    origin_airport: Mapped[
        Airport
    ] = relationship(
        Airport,

        foreign_keys=[
            origin_airport_id
        ],
    )

    destination_airport: Mapped[
        Airport
    ] = relationship(
        Airport,

        foreign_keys=[
            destination_airport_id
        ],
    )

    __table_args__ = (

        CheckConstraint(
            (
                "route_type IN "
                "('domestic', 'international')"
            ),
            name=(
                "ck_search_request_"
                "route_type"
            ),
        ),

        CheckConstraint(
            (
                "origin_airport_id "
                "<> "
                "destination_airport_id"
            ),
            name=(
                "ck_search_request_"
                "different_airports"
            ),
        ),
    )

    @property
    def departure_date_jalali(
        self,
    ) -> str:

        return format_jalali_date(
            self.departure_date
        )