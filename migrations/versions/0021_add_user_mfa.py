"""Add optional TOTP two-factor authentication fields to users

Revision ID: 0021_add_user_mfa
Revises: 0020_add_inference_jobs
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_add_user_mfa"
down_revision = "0020_add_inference_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
