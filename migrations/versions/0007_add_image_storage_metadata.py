"""Add image storage metadata

Revision ID: 0007_add_image_storage_metadata
Revises: 0006_add_alert_audit_fields
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_add_image_storage_metadata"
down_revision = "0006_add_alert_audit_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inspections",
        sa.Column("image_storage", sa.String(length=20), nullable=False, server_default="db"),
    )
    op.add_column("inspections", sa.Column("image_object_key", sa.String(length=500), nullable=True))
    op.add_column("inspections", sa.Column("image_size", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("inspections", "image_size")
    op.drop_column("inspections", "image_object_key")
    op.drop_column("inspections", "image_storage")
