"""Add per-account login-security fields (lockout + session revocation)

Revision ID: 0018_add_login_security
Revises: 0017_add_anpr_fields
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_add_login_security"
down_revision = "0017_add_anpr_fields"
branch_labels = None
depends_on = None


def upgrade():
    # Per-account brute-force throttle: count consecutive failures and lock the
    # account until a timestamp, independent of the per-IP rate limiter.
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    # Session revocation without a server-side store: bump this to invalidate all
    # of a user's existing signed-cookie sessions (logout-everywhere, password
    # reset, forced re-auth).
    op.add_column(
        "users",
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("users", "session_epoch")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
