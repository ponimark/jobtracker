"""Add rerank_score (cross-encoder score) to matches."""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("rerank_score", sa.Float(), nullable=True),
    )
    op.create_index(
        "matches_rerank_idx",
        "matches",
        ["profile_id", "rerank_score"],
    )


def downgrade() -> None:
    op.drop_index("matches_rerank_idx", table_name="matches")
    op.drop_column("matches", "rerank_score")
