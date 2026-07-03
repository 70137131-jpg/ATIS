"""Add alert workflow audit fields

Revision ID: 0006_add_alert_audit_fields
Revises: 0005_add_query_indexes
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_alert_audit_fields"
down_revision = "0005_add_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alerts", sa.Column("acknowledged_by_id", sa.Integer(), nullable=True))
    op.add_column("alerts", sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("resolved_by_id", sa.Integer(), nullable=True))
    op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("alerts") as batch:
        batch.create_foreign_key(
            "fk_alerts_acknowledged_by_id_users",
            "users",
            ["acknowledged_by_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_alerts_resolved_by_id_users",
            "users",
            ["resolved_by_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("alerts") as batch:
        batch.drop_constraint("fk_alerts_resolved_by_id_users", type_="foreignkey")
        batch.drop_constraint("fk_alerts_acknowledged_by_id_users", type_="foreignkey")
    op.drop_column("alerts", "resolved_at")
    op.drop_column("alerts", "resolved_by_id")
    op.drop_column("alerts", "acknowledged_at")
    op.drop_column("alerts", "acknowledged_by_id")
