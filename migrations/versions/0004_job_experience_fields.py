"""Add experience requirement fields to jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("experience_min_years", sa.Integer, nullable=True))
    op.add_column("jobs", sa.Column("experience_max_years", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "experience_max_years")
    op.drop_column("jobs", "experience_min_years")
