from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("outcome", sa.String(20), nullable=True))
    op.create_index("ix_jobs_finished_at", "jobs", ["finished_at"])
    op.execute("UPDATE jobs SET outcome = 'success', finished_at = NOW(), status = 'failed' WHERE status = 'done'")
    op.execute("UPDATE jobs SET outcome = 'error', finished_at = NOW() WHERE status = 'failed' AND outcome IS NULL")


def downgrade() -> None:
    op.execute("UPDATE jobs SET status = 'done' WHERE status = 'failed' AND outcome = 'success'")
    op.drop_index("ix_jobs_finished_at", table_name="jobs")
    op.drop_column("jobs", "outcome")
    op.drop_column("jobs", "finished_at")
    op.drop_column("jobs", "deadline_at")
