"""Add inference_jobs table for async (background) inference

Revision ID: 0020_add_inference_jobs
Revises: 0019_audit_hash_chain
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_add_inference_jobs"
down_revision = "0019_audit_hash_chain"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inference_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        # Captured inputs the background worker needs to run the inspection.
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("unique_name", sa.String(length=120), nullable=True),
        sa.Column("ext", sa.String(length=10), nullable=True),
        sa.Column("image_rel_path", sa.String(length=300), nullable=True),
        sa.Column("plate", sa.String(length=20), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("camera", sa.String(length=20), nullable=True),
        # Outputs.
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_inference_jobs_status", "inference_jobs", ["status"])
    op.create_index("ix_inference_jobs_created_by_id", "inference_jobs", ["created_by_id"])


def downgrade():
    op.drop_index("ix_inference_jobs_created_by_id", table_name="inference_jobs")
    op.drop_index("ix_inference_jobs_status", table_name="inference_jobs")
    op.drop_table("inference_jobs")
