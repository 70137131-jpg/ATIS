"""Add ANPR metadata fields

Revision ID: 0017_add_anpr_fields
Revises: 0016_add_saved_filters
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_add_anpr_fields"
down_revision = "0016_add_saved_filters"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inspections", sa.Column("plate_source", sa.String(length=30), nullable=True))
    op.add_column("inspections", sa.Column("plate_confidence", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("plate_raw_text", sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column("inspections", "plate_raw_text")
    op.drop_column("inspections", "plate_confidence")
    op.drop_column("inspections", "plate_source")
