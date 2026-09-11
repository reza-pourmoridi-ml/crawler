from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 1. Airlines
    op.create_table(
        "airlines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "official_name_fa",
            sa.String(length=255),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 2. Airline aliases
    op.create_table(
        "airline_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "airline_id",
            sa.Integer(),
            sa.ForeignKey("airlines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "alias_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "airline_id",
            "alias_name",
            name="uq_airline_alias",
        ),
    )

    op.create_index(
        "idx_airline_aliases_airline_id",
        "airline_aliases",
        ["airline_id"],
    )

    # Fuzzy search index
    op.execute(
        """
        CREATE INDEX idx_alias_name_trgm
        ON airline_aliases
        USING gin (alias_name gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alias_name_trgm")

    op.drop_index(
        "idx_airline_aliases_airline_id",
        table_name="airline_aliases",
    )

    op.drop_table("airline_aliases")
    op.drop_table("airlines")
