"""Add job alias mappings for cross-source deduplication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_aliases",
        sa.Column("alias_job_id", sa.Integer(), sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("canonical_job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("canonical_hash", BYTEA(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("job_aliases_canonical_idx", "job_aliases", ["canonical_job_id"])
    op.create_index("job_aliases_hash_idx", "job_aliases", ["canonical_hash"])


def downgrade() -> None:
    op.drop_index("job_aliases_hash_idx", table_name="job_aliases")
    op.drop_index("job_aliases_canonical_idx", table_name="job_aliases")
    op.drop_table("job_aliases")
