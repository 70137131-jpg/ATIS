"""Add user active flag

Revision ID: 0009_add_user_active_flag
Revises: 0008_add_inspection_audit_checksum
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_add_user_active_flag"
down_revision = "0008_add_inspection_audit_checksum"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    with op.batch_alter_table("users") as batch:
        batch.alter_column("is_active", server_default=None)


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_active")
