from datetime import (
    date,
    datetime,
)

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
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


class SearchProviderResult(Base):
    """Watermark for the newest persisted extraction of one provider."""

    __tablename__ = "search_provider_results"

    search_request_id: Mapped[int] = mapped_column(
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        primary_key=True,
    )
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    offers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class SearchAirlinePrice(Base):
    """Latest minimum for an airline within one search/provider result."""

    __tablename__ = "search_airline_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_request_id: Mapped[int] = mapped_column(
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    airline_id: Mapped[int] = mapped_column(
        ForeignKey("airlines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    departure_time: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "search_request_id",
            "website_id",
            "airline_id",
            name="uq_search_airline_price_provider",
        ),
        CheckConstraint("price > 0", name="ck_search_airline_price_positive"),
    )


class SearchLowestPrice(Base):
    """Persisted cross-provider minimum shown to the user."""

    __tablename__ = "search_lowest_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_request_id: Mapped[int] = mapped_column(
        ForeignKey("search_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    airline_id: Mapped[int] = mapped_column(
        ForeignKey("airlines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    departure_time: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "search_request_id",
            "airline_id",
            name="uq_search_lowest_price_airline",
        ),
        CheckConstraint("price > 0", name="ck_search_lowest_price_positive"),
    )
