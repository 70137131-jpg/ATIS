"""Add operational locations and cameras

Revision ID: 0015_add_operational_locations_cameras
Revises: 0014_add_inspection_model_metadata
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

revision = "0015_add_operational_locations_cameras"
down_revision = "0014_add_inspection_model_metadata"
branch_labels = None
depends_on = None


def _normalize(raw: str | None) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip()).lower()


def upgrade():
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("zone", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_locations_normalized_name", "locations", ["normalized_name"])
    op.create_index("ix_locations_zone", "locations", ["zone"])
    op.create_index("ix_locations_is_active", "locations", ["is_active"])

    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("normalized_name", sa.String(length=20), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("zone", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", "location_id", name="uq_cameras_name_location"),
    )
    op.create_index("ix_cameras_normalized_name", "cameras", ["normalized_name"])
    op.create_index("ix_cameras_location_id", "cameras", ["location_id"])
    op.create_index("ix_cameras_zone", "cameras", ["zone"])
    op.create_index("ix_cameras_is_active", "cameras", ["is_active"])
    op.create_index("ix_cameras_assigned_user_id", "cameras", ["assigned_user_id"])

    op.add_column("inspections", sa.Column("location_id", sa.Integer(), nullable=True))
    op.add_column("inspections", sa.Column("camera_id", sa.Integer(), nullable=True))
    op.create_index("ix_inspections_location_id", "inspections", ["location_id"])
    op.create_index("ix_inspections_camera_id", "inspections", ["camera_id"])
    with op.batch_alter_table("inspections") as batch:
        batch.create_foreign_key("fk_inspections_location_id_locations", "locations", ["location_id"], ["id"])
        batch.create_foreign_key("fk_inspections_camera_id_cameras", "cameras", ["camera_id"], ["id"])

    connection = op.get_bind()
    location_ids: dict[str, int] = {}
    camera_ids: dict[tuple[str, int | None], int] = {}
    rows = connection.execute(
        sa.text("SELECT id, location, camera FROM inspections")
    ).mappings()

    for row in rows:
        location_id = None
        normalized_location = _normalize(row["location"])
        if normalized_location:
            location_id = location_ids.get(normalized_location)
            if location_id is None:
                result = connection.execute(
                    sa.text(
                        "INSERT INTO locations (name, normalized_name, is_active, created_at) "
                        "VALUES (:name, :normalized_name, 1, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "name": (row["location"] or "Unknown Location")[:200],
                        "normalized_name": normalized_location[:200],
                    },
                )
                location_id = result.lastrowid
                if location_id is None:
                    location_id = connection.execute(
                        sa.text("SELECT id FROM locations WHERE normalized_name = :normalized_name"),
                        {"normalized_name": normalized_location[:200]},
                    ).scalar_one()
                location_ids[normalized_location] = location_id
            connection.execute(
                sa.text("UPDATE inspections SET location_id = :location_id WHERE id = :inspection_id"),
                {"location_id": location_id, "inspection_id": row["id"]},
            )

        normalized_camera = _normalize(row["camera"])
        if normalized_camera:
            camera_key = (normalized_camera[:20], location_id)
            camera_id = camera_ids.get(camera_key)
            if camera_id is None:
                result = connection.execute(
                    sa.text(
                        "INSERT INTO cameras (name, normalized_name, location_id, is_active, created_at) "
                        "VALUES (:name, :normalized_name, :location_id, 1, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "name": (row["camera"] or "")[:20],
                        "normalized_name": normalized_camera[:20],
                        "location_id": location_id,
                    },
                )
                camera_id = result.lastrowid
                if camera_id is None:
                    camera_id = connection.execute(
                        sa.text(
                            "SELECT id FROM cameras WHERE normalized_name = :normalized_name "
                            "AND ((location_id IS NULL AND :location_id IS NULL) OR location_id = :location_id)"
                        ),
                        {"normalized_name": normalized_camera[:20], "location_id": location_id},
                    ).scalar_one()
                camera_ids[camera_key] = camera_id
            connection.execute(
                sa.text("UPDATE inspections SET camera_id = :camera_id WHERE id = :inspection_id"),
                {"camera_id": camera_id, "inspection_id": row["id"]},
            )


def downgrade():
    with op.batch_alter_table("inspections") as batch:
        batch.drop_constraint("fk_inspections_camera_id_cameras", type_="foreignkey")
        batch.drop_constraint("fk_inspections_location_id_locations", type_="foreignkey")
    op.drop_index("ix_inspections_camera_id", table_name="inspections")
    op.drop_index("ix_inspections_location_id", table_name="inspections")
    op.drop_column("inspections", "camera_id")
    op.drop_column("inspections", "location_id")
    op.drop_index("ix_cameras_assigned_user_id", table_name="cameras")
    op.drop_index("ix_cameras_is_active", table_name="cameras")
    op.drop_index("ix_cameras_zone", table_name="cameras")
    op.drop_index("ix_cameras_location_id", table_name="cameras")
    op.drop_index("ix_cameras_normalized_name", table_name="cameras")
    op.drop_table("cameras")
    op.drop_index("ix_locations_is_active", table_name="locations")
    op.drop_index("ix_locations_zone", table_name="locations")
    op.drop_index("ix_locations_normalized_name", table_name="locations")
    op.drop_table("locations")
