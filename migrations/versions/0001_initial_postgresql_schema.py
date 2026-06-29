"""Initial PostgreSQL schema

Revision ID: 0001_initial_postgresql_schema
Revises:
Create Date: 2026-06-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_postgresql_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("plate", sa.String(length=20), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("camera", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("defects", sa.String(length=300), nullable=True),
        sa.Column("image_path", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("alerts")
    op.drop_table("inspections")
    op.drop_table("users")
