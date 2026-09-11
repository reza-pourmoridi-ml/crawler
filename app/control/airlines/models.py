from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db import Base


class Airline(Base):
    __tablename__ = "airlines"

    id: Mapped[int] = mapped_column(primary_key=True)

    official_name_fa: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    aliases: Mapped[list["AirlineAlias"]] = relationship(
        "AirlineAlias",
        back_populates="airline",
        cascade="all, delete-orphan",
    )


class AirlineAlias(Base):
    __tablename__ = "airline_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)

    airline_id: Mapped[int] = mapped_column(
        ForeignKey("airlines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alias_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    airline: Mapped[Airline] = relationship(
        "Airline",
        back_populates="aliases",
    )

    __table_args__ = (
        UniqueConstraint(
            "airline_id",
            "alias_name",
            name="uq_airline_alias",
        ),
    )