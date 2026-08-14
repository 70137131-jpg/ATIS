"""Migration chain integrity tests, plus execution of the 0023 backfill."""

import importlib.util
import re
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"

# Alembic's version table stores the current revision in VARCHAR(32). SQLite
# ignores the length, but PostgreSQL rejects longer IDs at upgrade time with
# "value too long for type character varying(32)".
ALEMBIC_VERSION_NUM_LIMIT = 32


def _revisions():
    revisions = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        text = path.read_text()
        revision = re.search(r"^revision = ['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision = (?:['\"]([^'\"]+)['\"]|None)", text, re.M)
        assert revision, f"{path.name} has no revision id"
        revisions[revision.group(1)] = down.group(1) if down and down.group(1) else None
    return revisions


def test_revision_ids_fit_alembic_version_column():
    for revision in _revisions():
        assert len(revision) <= ALEMBIC_VERSION_NUM_LIMIT, (
            f"revision id '{revision}' is {len(revision)} chars; PostgreSQL's "
            f"alembic_version.version_num column only holds {ALEMBIC_VERSION_NUM_LIMIT}."
        )


def test_migration_chain_is_linear_and_complete():
    revisions = _revisions()
    down_revisions = [d for d in revisions.values() if d is not None]
    # Every down_revision must exist, exactly one root, no duplicate parents.
    for down in down_revisions:
        assert down in revisions, f"down_revision '{down}' does not exist"
    assert list(revisions.values()).count(None) == 1, "expected exactly one root migration"
    assert len(set(down_revisions)) == len(down_revisions), "branching migration chain"
    # Exactly one head: a revision no other revision points down to.
    heads = set(revisions) - set(down_revisions)
    assert len(heads) == 1, f"expected exactly one head, found {sorted(heads)}"


def _load_migration(name):
    path = VERSIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pre_0023_schema(connection):
    """Create just the columns migration 0023 reads, at their pre-0023 shape."""
    connection.execute(sa.text(
        "CREATE TABLE inspections ("
        " id INTEGER PRIMARY KEY,"
        " status VARCHAR(10) NOT NULL,"
        " low_confidence BOOLEAN NOT NULL DEFAULT 0,"
        " predicted_class VARCHAR(80))"
    ))
    connection.execute(sa.text(
        "CREATE TABLE alerts ("
        " id INTEGER PRIMARY KEY,"
        " inspection_id INTEGER NOT NULL)"
    ))


def test_0023_backfills_outcome_and_alert_kind():
    """The backfill must derive correct values for rows written before the split.

    Runs the real migration module against a database at the 0022 shape, rather
    than re-implementing its logic, so a change to the migration is caught here.
    """
    engine = sa.create_engine("sqlite://")  # in-memory
    with engine.begin() as connection:
        _pre_0023_schema(connection)
        connection.execute(sa.text(
            "INSERT INTO inspections (id, status, low_confidence, predicted_class) VALUES"
            " (1, 'safe',   0, 'normal'),"      # passed
            " (2, 'unsafe', 0, 'cracked'),"     # real defect
            " (3, 'unsafe', 1, 'normal'),"      # low-confidence normal -> review
            " (4, 'unsafe', 0, 'not_tyre')"     # unworkable frame -> review
        ))
        # Historically only cracked and low-confidence rows produced alerts.
        connection.execute(sa.text(
            "INSERT INTO alerts (id, inspection_id) VALUES (10, 2), (11, 3)"
        ))

        context = MigrationContext.configure(connection)
        with Operations.context(context):
            _load_migration("0023_outcome_and_alert_kind").upgrade()

        outcomes = dict(connection.execute(sa.text(
            "SELECT id, outcome FROM inspections ORDER BY id"
        )).all())
        assert outcomes == {
            1: "safe",
            2: "unsafe",
            3: "needs_review",
            4: "needs_review",
        }

        kinds = dict(connection.execute(sa.text(
            "SELECT id, kind FROM alerts ORDER BY id"
        )).all())
        assert kinds == {10: "defect", 11: "review"}
