"""Store latest provider prices for asynchronous search results."""

from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_provider_results",
        sa.Column("search_request_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("source_job_id", sa.Integer(), nullable=False),
        sa.Column("offers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["search_request_id"], ["search_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("search_request_id", "website_id"),
    )
    op.create_index(
        "ix_search_provider_results_updated_at",
        "search_provider_results",
        ["updated_at"],
    )

    op.create_table(
        "search_airline_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("search_request_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("airline_id", sa.Integer(), nullable=False),
        sa.Column("source_job_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("departure_time", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_search_airline_price_positive"),
        sa.ForeignKeyConstraint(["airline_id"], ["airlines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["search_request_id"], ["search_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "search_request_id",
            "website_id",
            "airline_id",
            name="uq_search_airline_price_provider",
        ),
    )
    op.create_index("ix_search_airline_prices_airline_id", "search_airline_prices", ["airline_id"])
    op.create_index(
        "ix_search_airline_prices_search_request_id",
        "search_airline_prices",
        ["search_request_id"],
    )
    op.create_index("ix_search_airline_prices_updated_at", "search_airline_prices", ["updated_at"])
    op.create_index("ix_search_airline_prices_website_id", "search_airline_prices", ["website_id"])

    op.create_table(
        "search_lowest_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("search_request_id", sa.Integer(), nullable=False),
        sa.Column("airline_id", sa.Integer(), nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("source_job_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("departure_time", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_search_lowest_price_positive"),
        sa.ForeignKeyConstraint(["airline_id"], ["airlines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["search_request_id"], ["search_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "search_request_id",
            "airline_id",
            name="uq_search_lowest_price_airline",
        ),
    )
    op.create_index("ix_search_lowest_prices_airline_id", "search_lowest_prices", ["airline_id"])
    op.create_index(
        "ix_search_lowest_prices_search_request_id",
        "search_lowest_prices",
        ["search_request_id"],
    )
    op.create_index("ix_search_lowest_prices_updated_at", "search_lowest_prices", ["updated_at"])
    op.create_index("ix_search_lowest_prices_website_id", "search_lowest_prices", ["website_id"])


def downgrade() -> None:
    op.drop_index("ix_search_lowest_prices_website_id", table_name="search_lowest_prices")
    op.drop_index("ix_search_lowest_prices_updated_at", table_name="search_lowest_prices")
    op.drop_index("ix_search_lowest_prices_search_request_id", table_name="search_lowest_prices")
    op.drop_index("ix_search_lowest_prices_airline_id", table_name="search_lowest_prices")
    op.drop_table("search_lowest_prices")
    op.drop_index("ix_search_airline_prices_website_id", table_name="search_airline_prices")
    op.drop_index("ix_search_airline_prices_updated_at", table_name="search_airline_prices")
    op.drop_index("ix_search_airline_prices_search_request_id", table_name="search_airline_prices")
    op.drop_index("ix_search_airline_prices_airline_id", table_name="search_airline_prices")
    op.drop_table("search_airline_prices")
    op.drop_index("ix_search_provider_results_updated_at", table_name="search_provider_results")
    op.drop_table("search_provider_results")
