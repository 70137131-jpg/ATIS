"""Add inspection review workflow fields

Revision ID: 0011_review_workflow
Revises: 0010_add_audit_events
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_review_workflow"
down_revision = "0010_add_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inspections",
        sa.Column(
            "review_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.add_column("inspections", sa.Column("review_notes", sa.Text(), nullable=True))
    op.add_column("inspections", sa.Column("reviewer_id", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("inspections", sa.Column("correction_label", sa.String(length=80), nullable=True))
    op.create_index("ix_inspections_review_status", "inspections", ["review_status"])
    with op.batch_alter_table("inspections") as batch:
        batch.create_foreign_key(
            "fk_inspections_reviewer_id_users",
            "users",
            ["reviewer_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("inspections") as batch:
        batch.drop_constraint("fk_inspections_reviewer_id_users", type_="foreignkey")
    op.drop_index("ix_inspections_review_status", table_name="inspections")
    op.drop_column("inspections", "correction_label")
    op.drop_column("inspections", "reviewed_at")
    op.drop_column("inspections", "reviewer_id")
    op.drop_column("inspections", "review_notes")
    op.drop_column("inspections", "review_status")
