from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    String,
    func,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.infra.db import Base


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    domestic_url_format: Mapped[str | None] = (
        mapped_column(
            String(4096),
            nullable=True,
        )
    )

    international_url_format: Mapped[str | None] = (
        mapped_column(
            String(4096),
            nullable=True,
        )
    )

    date_calendar: Mapped[str | None] = (
        mapped_column(
            String(20),
            nullable=True,
        )
    )

    date_format: Mapped[str | None] = (
        mapped_column(
            String(32),
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            (
                "date_calendar IS NULL OR "
                "date_calendar IN "
                "('jalali', 'gregorian')"
            ),
            name="ck_website_date_calendar",
        ),
    )