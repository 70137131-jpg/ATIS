"""Replace plain-text users.password with hashed users.password_hash

Revision ID: 0002_password_hash
Revises: 0001_initial_postgresql_schema
Create Date: 2026-06-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash

revision = "0002_password_hash"
down_revision = "0001_initial_postgresql_schema"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add the new column as nullable so existing rows can be backfilled.
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )

    # 2. Backfill: hash any existing plain-text passwords into password_hash.
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("password", sa.String),
        sa.column("password_hash", sa.String),
    )
    conn = op.get_bind()
    for row in conn.execute(sa.select(users.c.id, users.c.password)).fetchall():
        raw = row[1] if row[1] is not None else ""
        conn.execute(
            users.update()
            .where(users.c.id == row[0])
            .values(password_hash=generate_password_hash(raw))
        )

    # 3. Enforce NOT NULL and drop the legacy plain-text column.
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "password_hash", existing_type=sa.String(length=255), nullable=False
        )
        batch.drop_column("password")


def downgrade():
    # Plain-text passwords cannot be recovered from hashes; restore an empty column.
    op.add_column(
        "users", sa.Column("password", sa.String(length=128), nullable=True)
    )
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")
