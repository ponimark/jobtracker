"""Add pgvector extension, embedding column, HNSW index, user_profile, matches tables,
and LISTEN/NOTIFY trigger

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column to jobs
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(384)")

    # HNSW index for cosine similarity queries
    op.execute(
        "CREATE INDEX IF NOT EXISTS jobs_embedding_hnsw ON jobs "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # User profile table
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("profile_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE user_profile ADD COLUMN embedding vector(384) NOT NULL DEFAULT array_fill(0, ARRAY[384])::vector")

    # Matches table
    op.create_table(
        "matches",
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("user_profile.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cosine", sa.Float, nullable=False),
        sa.Column("skill_overlap", sa.Float, nullable=False),
        sa.Column("recency", sa.Float, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("matches_score_idx", "matches", ["profile_id", "score"])

    # LISTEN/NOTIFY trigger: wakes the enricher on every new job insert
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_new_job() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('new_job', NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER jobs_notify
        AFTER INSERT ON jobs
        FOR EACH ROW EXECUTE FUNCTION notify_new_job();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS jobs_notify ON jobs")
    op.execute("DROP FUNCTION IF EXISTS notify_new_job()")
    op.drop_index("matches_score_idx")
    op.drop_table("matches")
    op.drop_table("user_profile")
    op.execute("DROP INDEX IF EXISTS jobs_embedding_hnsw")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
