"""Migration chain integrity tests."""

import re
from pathlib import Path

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
