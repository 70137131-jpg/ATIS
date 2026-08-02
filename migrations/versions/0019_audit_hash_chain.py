"""Add tamper-evident hash chain to audit_events

Revision ID: 0019_audit_hash_chain
Revises: 0018_add_login_security
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_audit_hash_chain"
down_revision = "0018_add_login_security"
branch_labels = None
depends_on = None


def upgrade():
    # Each event stores the previous event's hash and its own content hash, so a
    # silent edit/delete of any row breaks the chain from that point forward.
    # Existing (legacy) rows keep NULL hashes and are reported as pre-chain by the
    # verifier; the chain begins at the first row written after this migration.
    op.add_column("audit_events", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("entry_hash", sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column("audit_events", "entry_hash")
    op.drop_column("audit_events", "prev_hash")
