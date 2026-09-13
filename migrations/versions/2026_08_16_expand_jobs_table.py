from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "4c56bc50c745"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("type", sa.String(100), nullable=False, server_default="legacy"))
    op.add_column("jobs", sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"))
    op.add_column("jobs", sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"))
    op.add_column("jobs", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column("jobs", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("idx_jobs_pending", "jobs", ["type", "run_at"], postgresql_where=sa.text("status = 'pending'"))
    op.drop_column("jobs", "name")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("name", sa.String(100)))
    op.drop_index("idx_jobs_pending", table_name="jobs")
    for col in ["created_at", "run_at", "locked_until", "max_attempts", "attempts", "payload", "type"]:
        op.drop_column("jobs", col)
