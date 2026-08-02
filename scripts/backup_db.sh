#!/bin/sh
# backup_db.sh — Back up the ATIS database (SQLite or PostgreSQL).
#
# Reads DATABASE_URL (same variable the app uses). Writes a timestamped dump to
# the directory given as $1 (default ./backups). Postgres dumps use pg_dump's
# custom format (restore with pg_restore); SQLite uses the online `.backup`
# command so a running app does not corrupt the copy.
#
# Usage:
#   ./scripts/backup_db.sh [output_dir]
#
# Schedule from cron, e.g. hourly:
#   0 * * * * cd /app && ./scripts/backup_db.sh /var/backups/atis >> /var/log/atis-backup.log 2>&1
#
# IMPORTANT: a backup you have never restored is not a backup. Rehearse a
# restore into a scratch database at least once (see scripts/restore_db.sh and
# docs/data_governance.md) before trusting this in production.
set -eu

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
    # Match the app's default SQLite location.
    DB_URL="sqlite:///instance/atis.db"
fi

case "$DB_URL" in
    sqlite:*)
        # Strip the sqlite:/// prefix to a filesystem path.
        DB_PATH="$(printf '%s' "$DB_URL" | sed -E 's#^sqlite:/{2,3}##')"
        if [ ! -f "$DB_PATH" ]; then
            echo "ERROR: SQLite database not found at $DB_PATH" >&2
            exit 1
        fi
        DEST="$OUT_DIR/atis-sqlite-$STAMP.db"
        # .backup is a consistent online copy even while the app is writing.
        sqlite3 "$DB_PATH" ".backup '$DEST'"
        gzip -f "$DEST"
        echo "SQLite backup written: $DEST.gz"
        ;;
    postgres*|postgresql*)
        DEST="$OUT_DIR/atis-pg-$STAMP.dump"
        # pg_dump reads a libpq URL directly; -Fc is the compressed custom format.
        pg_dump --format=custom --no-owner --dbname="$DB_URL" --file="$DEST"
        echo "PostgreSQL backup written: $DEST"
        ;;
    *)
        echo "ERROR: unsupported DATABASE_URL scheme: $DB_URL" >&2
        exit 1
        ;;
esac
