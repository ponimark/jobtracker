"""Replace blended match scores with keyword/vector fields and skill lists."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("matches_score_idx", table_name="matches")

    op.add_column(
        "matches",
        sa.Column("keyword_score", sa.Float, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "matches",
        sa.Column("vector_score", sa.Float, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "matches",
        sa.Column(
            "matched_skills",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "missing_skills",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.drop_column("matches", "cosine")
    op.drop_column("matches", "skill_overlap")
    op.drop_column("matches", "recency")
    op.drop_column("matches", "score")

    op.create_index("matches_keyword_idx", "matches", ["profile_id", "keyword_score"])
    op.create_index("matches_vector_idx", "matches", ["profile_id", "vector_score"])


def downgrade() -> None:
    op.drop_index("matches_vector_idx", table_name="matches")
    op.drop_index("matches_keyword_idx", table_name="matches")

    op.add_column("matches", sa.Column("score", sa.Float, nullable=False, server_default=sa.text("0")))
    op.add_column("matches", sa.Column("recency", sa.Float, nullable=False, server_default=sa.text("0")))
    op.add_column("matches", sa.Column("skill_overlap", sa.Float, nullable=False, server_default=sa.text("0")))
    op.add_column("matches", sa.Column("cosine", sa.Float, nullable=False, server_default=sa.text("0")))

    op.drop_column("matches", "missing_skills")
    op.drop_column("matches", "matched_skills")
    op.drop_column("matches", "vector_score")
    op.drop_column("matches", "keyword_score")

    op.create_index("matches_score_idx", "matches", ["profile_id", "score"])
