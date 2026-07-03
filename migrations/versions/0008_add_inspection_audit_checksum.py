"""Add inspection audit and image checksum fields

Revision ID: 0008_add_inspection_audit_checksum
Revises: 0007_add_image_storage_metadata
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_inspection_audit_checksum"
down_revision = "0007_add_image_storage_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inspections", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("image_checksum", sa.String(length=64), nullable=True))
    op.create_index("ix_inspections_image_checksum", "inspections", ["image_checksum"])
    with op.batch_alter_table("inspections") as batch:
        batch.create_foreign_key(
            "fk_inspections_created_by_id_users",
            "users",
            ["created_by_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("inspections") as batch:
        batch.drop_constraint("fk_inspections_created_by_id_users", type_="foreignkey")
    op.drop_index("ix_inspections_image_checksum", table_name="inspections")
    op.drop_column("inspections", "image_checksum")
    op.drop_column("inspections", "created_by_id")
