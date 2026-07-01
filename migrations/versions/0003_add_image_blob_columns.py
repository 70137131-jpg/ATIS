"""Add image_data and image_mime columns to inspections

Revision ID: 0003_add_image_blob_columns
Revises: 0002_password_hash
Create Date: 2026-07-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_image_blob_columns"
down_revision = "0002_password_hash"
branch_labels = None
depends_on = None


def upgrade():
    # Durable image storage: raw bytes live in the DB so uploads survive
    # ephemeral container filesystems (served via /media/inspection/<id>).
    op.add_column(
        "inspections", sa.Column("image_data", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "inspections", sa.Column("image_mime", sa.String(length=50), nullable=True)
    )


def downgrade():
    with op.batch_alter_table("inspections") as batch:
        batch.drop_column("image_mime")
        batch.drop_column("image_data")
