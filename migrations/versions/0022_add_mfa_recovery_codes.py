"""Add MFA recovery (backup) codes to users

Revision ID: 0022_add_mfa_recovery_codes
Revises: 0021_add_user_mfa
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_add_mfa_recovery_codes"
down_revision = "0021_add_user_mfa"
branch_labels = None
depends_on = None


def upgrade():
    # JSON list of *hashed* single-use recovery codes; plaintext is shown once at
    # generation and never stored.
    op.add_column("users", sa.Column("mfa_recovery_codes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("users", "mfa_recovery_codes")
