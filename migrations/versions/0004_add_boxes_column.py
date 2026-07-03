"""Add boxes column to inspections

Revision ID: 0004_add_boxes_column
Revises: 0003_add_image_blob_columns
Create Date: 2026-07-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_boxes_column"
down_revision = "0003_add_image_blob_columns"
branch_labels = None
depends_on = None


def upgrade():
    # Persist the detector's per-defect boxes (JSON) so the inspection detail
    # page can redraw the real bounding boxes over the stored image.
    op.add_column(
        "inspections", sa.Column("boxes", sa.Text(), nullable=True)
    )


def downgrade():
    with op.batch_alter_table("inspections") as batch:
        batch.drop_column("boxes")
