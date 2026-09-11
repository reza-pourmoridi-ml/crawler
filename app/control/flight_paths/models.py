from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.control.airports.models import Airport
from app.control.websites.models import Website
from app.infra.db import Base


class FlightPath(Base):
    """An optional website-specific code for a shared airport."""

    __tablename__ = "flight_paths"
    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    airport_id: Mapped[int] = mapped_column(
        ForeignKey("airports.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    code: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    website: Mapped[Website] = relationship(Website)
    airport: Mapped[Airport] = relationship(Airport, back_populates="codes")

    @property
    def airport_name_fa(self) -> str:
        return self.airport.name_fa

    __table_args__ = (
        UniqueConstraint("website_id", "code", name="uq_flight_path_website_code"),
        UniqueConstraint("website_id", "airport_id", name="uq_flight_path_website_airport"),
    )
