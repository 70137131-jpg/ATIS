"""Add saved filters

Revision ID: 0016_add_saved_filters
Revises: 0015_locations_cameras
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_add_saved_filters"
down_revision = "0015_locations_cameras"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("page", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "page", "name", name="uq_saved_filters_user_page_name"),
    )
    op.create_index("ix_saved_filters_user_id", "saved_filters", ["user_id"])
    op.create_index("ix_saved_filters_page", "saved_filters", ["page"])


def downgrade():
    op.drop_index("ix_saved_filters_page", table_name="saved_filters")
    op.drop_index("ix_saved_filters_user_id", table_name="saved_filters")
    op.drop_table("saved_filters")
