"""Enrich alert workflow

Revision ID: 0013_enrich_alert_workflow
Revises: 0012_normalize_defects
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_enrich_alert_workflow"
down_revision = "0012_normalize_defects"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alerts", sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"))
    op.add_column("alerts", sa.Column("severity", sa.String(length=20), nullable=False, server_default="major"))
    op.add_column("alerts", sa.Column("assigned_user_id", sa.Integer(), nullable=True))
    op.add_column("alerts", sa.Column("assigned_team", sa.String(length=80), nullable=True))
    op.add_column("alerts", sa.Column("sla_due_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("escalation_status", sa.String(length=30), nullable=False, server_default="none"))
    op.add_column("alerts", sa.Column("resolution_category", sa.String(length=50), nullable=True))
    op.create_index("ix_alerts_priority", "alerts", ["priority"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_assigned_user_id", "alerts", ["assigned_user_id"])
    op.create_index("ix_alerts_sla_due_at", "alerts", ["sla_due_at"])
    op.create_index("ix_alerts_escalation_status", "alerts", ["escalation_status"])
    with op.batch_alter_table("alerts") as batch:
        batch.create_foreign_key(
            "fk_alerts_assigned_user_id_users",
            "users",
            ["assigned_user_id"],
            ["id"],
        )

    op.create_table(
        "alert_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("comment_type", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_comments_alert_id", "alert_comments", ["alert_id"])
    op.create_index("ix_alert_comments_author_id", "alert_comments", ["author_id"])
    op.create_index("ix_alert_comments_comment_type", "alert_comments", ["comment_type"])
    op.create_index("ix_alert_comments_created_at", "alert_comments", ["created_at"])


def downgrade():
    op.drop_index("ix_alert_comments_created_at", table_name="alert_comments")
    op.drop_index("ix_alert_comments_comment_type", table_name="alert_comments")
    op.drop_index("ix_alert_comments_author_id", table_name="alert_comments")
    op.drop_index("ix_alert_comments_alert_id", table_name="alert_comments")
    op.drop_table("alert_comments")
    with op.batch_alter_table("alerts") as batch:
        batch.drop_constraint("fk_alerts_assigned_user_id_users", type_="foreignkey")
    op.drop_index("ix_alerts_escalation_status", table_name="alerts")
    op.drop_index("ix_alerts_sla_due_at", table_name="alerts")
    op.drop_index("ix_alerts_assigned_user_id", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_priority", table_name="alerts")
    op.drop_column("alerts", "resolution_category")
    op.drop_column("alerts", "escalation_status")
    op.drop_column("alerts", "sla_due_at")
    op.drop_column("alerts", "assigned_team")
    op.drop_column("alerts", "assigned_user_id")
    op.drop_column("alerts", "severity")
    op.drop_column("alerts", "priority")
