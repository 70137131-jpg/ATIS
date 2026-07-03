"""Add indexes for high-volume dashboard queries

Revision ID: 0005_add_query_indexes
Revises: 0004_add_boxes_column
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op

revision = "0005_add_query_indexes"
down_revision = "0004_add_boxes_column"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_inspections_timestamp", "inspections", ["timestamp"])
    op.create_index("ix_inspections_plate", "inspections", ["plate"])
    op.create_index("ix_inspections_status", "inspections", ["status"])
    op.create_index("ix_alerts_inspection_id", "alerts", ["inspection_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])


def downgrade():
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_inspection_id", table_name="alerts")
    op.drop_index("ix_inspections_status", table_name="inspections")
    op.drop_index("ix_inspections_plate", table_name="inspections")
    op.drop_index("ix_inspections_timestamp", table_name="inspections")
