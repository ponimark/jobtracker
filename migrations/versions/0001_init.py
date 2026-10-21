"""Initial schema: sources, jobs, jobs_raw, fetch_log

Revision ID: 0001
Revises:
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ats", sa.Text, nullable=False),
        sa.Column("company_slug", sa.Text, nullable=False),
        sa.Column("company_name", sa.Text, nullable=True),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("poll_interval_s", sa.Integer, nullable=False, server_default="60"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_polled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_etag", sa.Text, nullable=True),
        sa.Column("last_modified", sa.Text, nullable=True),
        sa.Column("last_status", sa.Integer, nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("ats", "company_slug", name="uq_sources_ats_slug"),
    )
    op.create_index("ix_sources_ats", "sources", ["ats"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("canonical_hash", sa.LargeBinary, nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("company", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("remote", sa.Boolean, nullable=True),
        sa.Column("employment_type", sa.Text, nullable=True),
        sa.Column("seniority", sa.Text, nullable=True),
        sa.Column("salary_min", sa.Integer, nullable=True),
        sa.Column("salary_max", sa.Integer, nullable=True),
        sa.Column("salary_currency", sa.Text, nullable=True),
        sa.Column("description_html", sa.Text, nullable=True),
        sa.Column("description_text", sa.Text, nullable=True),
        sa.Column("apply_url", sa.Text, nullable=False),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("removed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("embedded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("source_id", "external_id", name="uq_jobs_source_external"),
    )
    op.create_index("jobs_canonical_hash_idx", "jobs", ["canonical_hash"])
    op.create_index("jobs_first_seen_idx", "jobs", ["first_seen_at"])
    op.create_index("ix_jobs_source_id", "jobs", ["source_id"])

    op.create_table(
        "jobs_raw",
        sa.Column("job_id", sa.BigInteger, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), primary_key=True, server_default=sa.text("NOW()")),
        sa.Column("payload", JSONB, nullable=False),
    )

    op.create_table(
        "fetch_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.Integer, nullable=True),
        sa.Column("new_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fetch_log")
    op.drop_table("jobs_raw")
    op.drop_table("jobs")
    op.drop_table("sources")
