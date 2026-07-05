"""Add inspection model metadata

Revision ID: 0014_model_metadata
Revises: 0013_enrich_alert_workflow
Create Date: 2026-07-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_model_metadata"
down_revision = "0013_enrich_alert_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inspections", sa.Column("predicted_class", sa.String(length=80), nullable=True))
    op.add_column("inspections", sa.Column("model_path", sa.String(length=300), nullable=True))
    op.add_column("inspections", sa.Column("model_version", sa.String(length=64), nullable=True))
    op.add_column("inspections", sa.Column("model_threshold", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("inspections", sa.Column("inference_ms", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("inspections", "inference_ms")
    op.drop_column("inspections", "low_confidence")
    op.drop_column("inspections", "model_threshold")
    op.drop_column("inspections", "model_version")
    op.drop_column("inspections", "model_path")
    op.drop_column("inspections", "predicted_class")
