from alembic import op
import sqlalchemy as sa

revision = "4c56bc50c745"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
    )


def downgrade() -> None:
    op.drop_table("jobs")

