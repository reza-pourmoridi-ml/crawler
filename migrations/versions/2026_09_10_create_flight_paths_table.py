"""Map one airport to its URL code on one website."""

from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flight_paths",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "website_id", sa.Integer(),
            sa.ForeignKey("websites.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("airport_name_fa", sa.String(255), nullable=False),
        sa.Column("code", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("website_id", "code", name="uq_flight_path_website_code"),
        sa.UniqueConstraint(
            "website_id", "airport_name_fa", name="uq_flight_path_website_airport",
        ),
    )
    op.create_index("ix_flight_paths_website_id", "flight_paths", ["website_id"])


def downgrade() -> None:
    op.drop_index("ix_flight_paths_website_id", table_name="flight_paths")
    op.drop_table("flight_paths")
