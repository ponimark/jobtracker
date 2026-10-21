"""Unique user_profile.name for track profiles (DE / AIML)."""
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_user_profile_name", "user_profile", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_user_profile_name", "user_profile", type_="unique")
