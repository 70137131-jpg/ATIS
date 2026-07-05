"""Normalize inspection defects

Revision ID: 0012_normalize_defects
Revises: 0011_review_workflow
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

revision = "0012_normalize_defects"
down_revision = "0011_review_workflow"
branch_labels = None
depends_on = None


def _display_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def _normalized_name(raw: str) -> str:
    return _display_name(raw).lower()


def upgrade():
    op.create_table(
        "defect_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_defect_types_normalized_name", "defect_types", ["normalized_name"])

    op.create_table(
        "inspection_defects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("defect_type_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.Text(), nullable=True),
        sa.Column("model_source", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["defect_type_id"], ["defect_types.id"]),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspection_defects_defect_type_id", "inspection_defects", ["defect_type_id"])
    op.create_index("ix_inspection_defects_inspection_id", "inspection_defects", ["inspection_id"])

    connection = op.get_bind()
    defect_type_ids: dict[str, int] = {}

    rows = connection.execute(
        sa.text("SELECT id, defects, confidence FROM inspections WHERE defects IS NOT NULL AND defects != ''")
    ).mappings()
    for row in rows:
        for raw_part in row["defects"].split(","):
            name = _display_name(raw_part)
            if not name:
                continue
            normalized = _normalized_name(name)
            defect_type_id = defect_type_ids.get(normalized)
            if defect_type_id is None:
                result = connection.execute(
                    sa.text(
                        "INSERT INTO defect_types (name, normalized_name, created_at) "
                        "VALUES (:name, :normalized_name, CURRENT_TIMESTAMP)"
                    ),
                    {"name": name[:80], "normalized_name": normalized[:80]},
                )
                defect_type_id = result.lastrowid
                if defect_type_id is None:
                    defect_type_id = connection.execute(
                        sa.text("SELECT id FROM defect_types WHERE normalized_name = :normalized_name"),
                        {"normalized_name": normalized[:80]},
                    ).scalar_one()
                defect_type_ids[normalized] = defect_type_id

            connection.execute(
                sa.text(
                    "INSERT INTO inspection_defects "
                    "(inspection_id, defect_type_id, confidence, model_source, created_at) "
                    "VALUES (:inspection_id, :defect_type_id, :confidence, :model_source, CURRENT_TIMESTAMP)"
                ),
                {
                    "inspection_id": row["id"],
                    "defect_type_id": defect_type_id,
                    "confidence": row["confidence"],
                    "model_source": "legacy_defects_column",
                },
            )


def downgrade():
    op.drop_index("ix_inspection_defects_inspection_id", table_name="inspection_defects")
    op.drop_index("ix_inspection_defects_defect_type_id", table_name="inspection_defects")
    op.drop_table("inspection_defects")
    op.drop_index("ix_defect_types_normalized_name", table_name="defect_types")
    op.drop_table("defect_types")
