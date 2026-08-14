"""Add Inspection.outcome and Alert.kind (three-way verdict split)

Splits the safety verdict into safe / needs_review / unsafe without changing the
meaning of the existing binary ``inspections.status``, so every report, metric
and dashboard that reads status keeps its current numbers. ``outcome`` carries
the finer distinction and ``alerts.kind`` tags whether an alert is real defect
work or a review item.

Both columns are added with a server default and backfilled from data already on
the rows, so existing installations get correct values without a manual step.

Revision ID: 0023_outcome_and_alert_kind
Revises: 0022_add_mfa_recovery_codes
Create Date: 2026-08-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0023_outcome_and_alert_kind"
down_revision = "0022_add_mfa_recovery_codes"
branch_labels = None
depends_on = None


# Lightweight table stubs so the backfill is written as SQLAlchemy expressions
# rather than raw SQL — boolean comparisons differ between SQLite and Postgres.
inspections = sa.table(
    "inspections",
    sa.column("id", sa.Integer),
    sa.column("status", sa.String),
    sa.column("outcome", sa.String),
    sa.column("low_confidence", sa.Boolean),
    sa.column("predicted_class", sa.String),
)
alerts = sa.table(
    "alerts",
    sa.column("inspection_id", sa.Integer),
    sa.column("kind", sa.String),
)


def upgrade():
    op.add_column(
        "inspections",
        sa.Column("outcome", sa.String(20), nullable=False, server_default="unsafe"),
    )
    op.create_index("ix_inspections_outcome", "inspections", ["outcome"])
    op.add_column(
        "alerts",
        sa.Column("kind", sa.String(20), nullable=False, server_default="defect"),
    )
    op.create_index("ix_alerts_kind", "alerts", ["kind"])

    # Backfill outcome. Anything already passed stays safe; anything withheld
    # for low confidence or as a non-tyre frame becomes needs_review; the rest
    # (real cracked verdicts) keeps the "unsafe" server default.
    op.execute(
        inspections.update()
        .where(inspections.c.status == "safe")
        .values(outcome="safe")
    )
    op.execute(
        inspections.update()
        .where(
            sa.and_(
                inspections.c.status != "safe",
                sa.or_(
                    inspections.c.low_confidence.is_(True),
                    inspections.c.predicted_class == "not_tyre",
                ),
            )
        )
        .values(outcome="needs_review")
    )

    # Backfill alert kind from the inspection each alert points at. Historically
    # only low-confidence normals produced non-defect alerts (not-tyre frames
    # never created one), so that condition is the whole of it.
    op.execute(
        alerts.update()
        .where(
            alerts.c.inspection_id.in_(
                sa.select(inspections.c.id).where(
                    sa.and_(
                        inspections.c.low_confidence.is_(True),
                        inspections.c.status != "safe",
                    )
                )
            )
        )
        .values(kind="review")
    )


def downgrade():
    op.drop_index("ix_alerts_kind", table_name="alerts")
    op.drop_column("alerts", "kind")
    op.drop_index("ix_inspections_outcome", table_name="inspections")
    op.drop_column("inspections", "outcome")
