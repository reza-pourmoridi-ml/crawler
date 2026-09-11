from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db import Base


class Airport(Base):
    """A shared airport, classified relative to Iran, independent of websites."""

    __tablename__ = "airports"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_fa: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    codes: Mapped[list["FlightPath"]] = relationship(
        "FlightPath", back_populates="airport", cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("category IN ('domestic', 'international')", name="ck_airport_category"),
    )
