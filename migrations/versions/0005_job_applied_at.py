"""Add applied_at to jobs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("applied_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "applied_at")
