#!/bin/sh
# restore_db.sh — Restore an ATIS database backup produced by backup_db.sh.
#
# Usage:
#   ./scripts/restore_db.sh <backup_file> [target_DATABASE_URL]
#
# If target_DATABASE_URL is omitted, DATABASE_URL from the environment is used.
# ALWAYS rehearse a restore into a scratch/staging database first — never point
# this at production on your first run. This script refuses to run unless
# ATIS_RESTORE_CONFIRM=yes is set, so a restore can never be a fat-finger away.
#
#   ATIS_RESTORE_CONFIRM=yes ./scripts/restore_db.sh \
#       backups/atis-pg-20260802T010000Z.dump \
#       postgresql://user:pass@staging-host:5432/atis_scratch
set -eu

BACKUP_FILE="${1:?usage: restore_db.sh <backup_file> [target_DATABASE_URL]}"
TARGET_URL="${2:-${DATABASE_URL:-sqlite:///instance/atis.db}}"

if [ "${ATIS_RESTORE_CONFIRM:-}" != "yes" ]; then
    echo "Refusing to restore without ATIS_RESTORE_CONFIRM=yes." >&2
    echo "Target: $TARGET_URL" >&2
    echo "Rehearse into a scratch database first. See docs/data_governance.md." >&2
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

case "$TARGET_URL" in
    sqlite:*)
        DB_PATH="$(printf '%s' "$TARGET_URL" | sed -E 's#^sqlite:/{2,3}##')"
        mkdir -p "$(dirname "$DB_PATH")"
        case "$BACKUP_FILE" in
            *.gz) gunzip -c "$BACKUP_FILE" > "$DB_PATH" ;;
            *)    cp "$BACKUP_FILE" "$DB_PATH" ;;
        esac
        echo "Restored SQLite database to $DB_PATH"
        ;;
    postgres*|postgresql*)
        # --clean drops objects before recreating them; run against an empty or
        # disposable database. pg_restore reads the custom (-Fc) dump format.
        pg_restore --clean --if-exists --no-owner --dbname="$TARGET_URL" "$BACKUP_FILE"
        echo "Restored PostgreSQL database from $BACKUP_FILE"
        ;;
    *)
        echo "ERROR: unsupported target DATABASE_URL scheme: $TARGET_URL" >&2
        exit 1
        ;;
esac
