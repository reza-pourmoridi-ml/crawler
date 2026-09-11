"""Replace website base URL with search URL formats."""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column(
            "domestic_url_format",
            sa.String(4096),
            nullable=True,
        ),
    )

    op.add_column(
        "websites",
        sa.Column(
            "international_url_format",
            sa.String(4096),
            nullable=True,
        ),
    )

    op.add_column(
        "websites",
        sa.Column(
            "date_calendar",
            sa.String(20),
            nullable=True,
        ),
    )

    op.add_column(
        "websites",
        sa.Column(
            "date_format",
            sa.String(32),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_website_date_calendar",
        "websites",
        (
            "date_calendar IS NULL OR "
            "date_calendar IN ('jalali', 'gregorian')"
        ),
    )

    op.drop_column(
        "websites",
        "base_url",
    )


def downgrade() -> None:
    op.add_column(
        "websites",
        sa.Column(
            "base_url",
            sa.String(2048),
            nullable=True,
        ),
    )

    op.drop_constraint(
        "ck_website_date_calendar",
        "websites",
        type_="check",
    )

    op.drop_column(
        "websites",
        "date_format",
    )

    op.drop_column(
        "websites",
        "date_calendar",
    )

    op.drop_column(
        "websites",
        "international_url_format",
    )

    op.drop_column(
        "websites",
        "domestic_url_format",
    )