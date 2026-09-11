"""Create flight search requests table."""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"

down_revision = "f1a2b3c4d5e6"

branch_labels = None

depends_on = None


def upgrade() -> None:

    op.create_table(
        "search_requests",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "origin_airport_id",
            sa.Integer(),

            sa.ForeignKey(
                "airports.id",
                ondelete="RESTRICT",
            ),

            nullable=False,
        ),

        sa.Column(
            "destination_airport_id",
            sa.Integer(),

            sa.ForeignKey(
                "airports.id",
                ondelete="RESTRICT",
            ),

            nullable=False,
        ),

        sa.Column(
            "departure_date",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "created_at",

            sa.DateTime(
                timezone=True
            ),

            server_default=
                sa.func.now(),

            nullable=False,
        ),

        sa.CheckConstraint(
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


    op.create_index(
        "ix_search_requests_origin_airport_id",

        "search_requests",

        ["origin_airport_id"],
    )


    op.create_index(
        "ix_search_requests_destination_airport_id",

        "search_requests",

        ["destination_airport_id"],
    )


    op.create_index(
        "ix_search_requests_departure_date",

        "search_requests",

        ["departure_date"],
    )


def downgrade() -> None:

    op.drop_index(
        "ix_search_requests_departure_date",
        table_name="search_requests",
    )

    op.drop_index(
        (
            "ix_search_requests_"
            "destination_airport_id"
        ),
        table_name="search_requests",
    )

    op.drop_index(
        (
            "ix_search_requests_"
            "origin_airport_id"
        ),
        table_name="search_requests",
    )

    op.drop_table(
        "search_requests"
    )