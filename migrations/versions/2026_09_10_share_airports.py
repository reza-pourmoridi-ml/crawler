"""Share airports across websites, preserving existing mapping IDs and codes.

Legacy records have no category, so they start as domestic and can be reclassified
in the control panel. Downgrade preserves mappings but cannot retain category or
shared airports that have no website codes in the old schema.
"""
from alembic import op
import sqlalchemy as sa

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "airports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_fa", sa.String(255), nullable=False, unique=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("category IN ('domestic', 'international')", name="ck_airport_category"),
    )
    op.create_index("ix_airports_category", "airports", ["category"])
    op.execute("""
        INSERT INTO airports (name_fa, category, created_at)
        SELECT airport_name_fa, 'domestic', MIN(created_at)
        FROM flight_paths GROUP BY airport_name_fa ORDER BY airport_name_fa
    """)
    op.add_column("flight_paths", sa.Column("airport_id", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE flight_paths SET airport_id = airports.id
        FROM airports WHERE airports.name_fa = flight_paths.airport_name_fa
    """)
    op.alter_column("flight_paths", "airport_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key("fk_flight_paths_airport_id", "flight_paths", "airports", ["airport_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_flight_paths_airport_id", "flight_paths", ["airport_id"])
    op.drop_constraint("uq_flight_path_website_airport", "flight_paths", type_="unique")
    op.create_unique_constraint("uq_flight_path_website_airport", "flight_paths", ["website_id", "airport_id"])
    op.drop_column("flight_paths", "airport_name_fa")


def downgrade() -> None:
    op.add_column("flight_paths", sa.Column("airport_name_fa", sa.String(255), nullable=True))
    op.execute("""
        UPDATE flight_paths SET airport_name_fa = airports.name_fa
        FROM airports WHERE airports.id = flight_paths.airport_id
    """)
    op.alter_column("flight_paths", "airport_name_fa", existing_type=sa.String(255), nullable=False)
    op.drop_constraint("uq_flight_path_website_airport", "flight_paths", type_="unique")
    op.create_unique_constraint("uq_flight_path_website_airport", "flight_paths", ["website_id", "airport_name_fa"])
    op.drop_constraint("fk_flight_paths_airport_id", "flight_paths", type_="foreignkey")
    op.drop_index("ix_flight_paths_airport_id", table_name="flight_paths")
    op.drop_column("flight_paths", "airport_id")
    op.drop_index("ix_airports_category", table_name="airports")
    op.drop_table("airports")
