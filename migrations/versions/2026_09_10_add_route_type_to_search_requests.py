"""Add route type to search requests."""

from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_requests",
        sa.Column(
            "route_type",
            sa.String(20),
            nullable=True,
        ),
    )

    # مقداردهی درخواست‌های قبلی
    op.execute(
        """
        UPDATE search_requests AS sr
        SET route_type = CASE
            WHEN EXISTS (
                SELECT 1
                FROM airports AS origin_airport
                WHERE origin_airport.id = sr.origin_airport_id
                  AND origin_airport.category = 'domestic'
            )
            AND EXISTS (
                SELECT 1
                FROM airports AS destination_airport
                WHERE destination_airport.id = sr.destination_airport_id
                  AND destination_airport.category = 'domestic'
            )
            THEN 'domestic'
            ELSE 'international'
        END
        """
    )

    op.alter_column(
        "search_requests",
        "route_type",
        existing_type=sa.String(20),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_search_request_route_type",
        "search_requests",
        "route_type IN ('domestic', 'international')",
    )

    op.create_index(
        "ix_search_requests_route_type",
        "search_requests",
        ["route_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_search_requests_route_type",
        table_name="search_requests",
    )

    op.drop_constraint(
        "ck_search_request_route_type",
        "search_requests",
        type_="check",
    )

    op.drop_column(
        "search_requests",
        "route_type",
    )