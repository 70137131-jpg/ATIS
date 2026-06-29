"""
Copy existing ATIS data from SQLite into the configured PostgreSQL database.

Run after applying migrations:
    python3 migrate_sqlite_to_postgres.py

Use --replace only when you intentionally want to clear PostgreSQL first:
    python3 migrate_sqlite_to_postgres.py --replace
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import app
from models import Alert, Inspection, User, db


DEFAULT_SQLITE_PATH = Path("instance/atis.db")
TABLES = ("users", "inspections", "alerts")

RESET_SEQUENCE_SQL = {
    "users": """
        SELECT setval(
            pg_get_serial_sequence('users', 'id'),
            COALESCE((SELECT MAX(id) FROM users), 1),
            (SELECT MAX(id) FROM users) IS NOT NULL
        )
    """,
    "inspections": """
        SELECT setval(
            pg_get_serial_sequence('inspections', 'id'),
            COALESCE((SELECT MAX(id) FROM inspections), 1),
            (SELECT MAX(id) FROM inspections) IS NOT NULL
        )
    """,
    "alerts": """
        SELECT setval(
            pg_get_serial_sequence('alerts', 'id'),
            COALESCE((SELECT MAX(id) FROM alerts), 1),
            (SELECT MAX(id) FROM alerts) IS NOT NULL
        )
    """,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate ATIS data from SQLite into PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(DEFAULT_SQLITE_PATH),
        help="Path to the source SQLite database file.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing PostgreSQL rows before importing SQLite data.",
    )
    return parser.parse_args()


def parse_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def fetch_sqlite_rows(sqlite_path):
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite source database not found: {sqlite_path}")

    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = {}
        for table in TABLES:
            rows[table] = [
                dict(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")
            ]
        return rows
    finally:
        connection.close()


def get_postgres_counts():
    return {
        "users": User.query.count(),
        "inspections": Inspection.query.count(),
        "alerts": Alert.query.count(),
    }


def clear_postgres_rows():
    Alert.query.delete()
    Inspection.query.delete()
    User.query.delete()
    db.session.commit()


def reset_postgres_sequences():
    for sql in RESET_SEQUENCE_SQL.values():
        db.session.execute(text(sql))
    db.session.commit()


def import_rows(rows):
    users = [
        User(
            id=row["id"],
            email=row["email"],
            password=row["password"],
            role=row["role"],
            created_at=parse_datetime(row["created_at"]),
        )
        for row in rows["users"]
    ]
    db.session.add_all(users)
    db.session.flush()

    inspections = [
        Inspection(
            id=row["id"],
            timestamp=parse_datetime(row["timestamp"]),
            plate=row["plate"],
            location=row["location"],
            camera=row["camera"],
            status=row["status"],
            confidence=row["confidence"],
            defects=row["defects"],
            image_path=row["image_path"],
        )
        for row in rows["inspections"]
    ]
    db.session.add_all(inspections)
    db.session.flush()

    alerts = [
        Alert(
            id=row["id"],
            inspection_id=row["inspection_id"],
            status=row["status"],
            response=row["response"],
            created_at=parse_datetime(row["created_at"]),
        )
        for row in rows["alerts"]
    ]
    db.session.add_all(alerts)
    db.session.commit()


def main():
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    sqlite_rows = fetch_sqlite_rows(sqlite_path)

    with app.app_context():
        if db.engine.url.get_backend_name() != "postgresql":
            raise SystemExit(
                "Refusing to migrate because DATABASE_URL is not PostgreSQL: "
                f"{db.engine.url.render_as_string(hide_password=True)}"
            )

        try:
            existing_counts = get_postgres_counts()
        except SQLAlchemyError as exc:
            raise SystemExit(
                "Could not read PostgreSQL tables. Run migrations first with:\n"
                "  python3 -m flask --app app db upgrade\n\n"
                f"Database error: {exc}"
            ) from exc

        if any(existing_counts.values()) and not args.replace:
            counts = ", ".join(
                f"{table}={count}" for table, count in existing_counts.items()
            )
            raise SystemExit(
                "PostgreSQL already contains data "
                f"({counts}). Re-run with --replace to clear it first."
            )

        try:
            if args.replace:
                clear_postgres_rows()
            import_rows(sqlite_rows)
            reset_postgres_sequences()
        except Exception:
            db.session.rollback()
            raise

        final_counts = get_postgres_counts()
        print("Migration complete.")
        for table in TABLES:
            print(f"{table}: {final_counts[table]}")


if __name__ == "__main__":
    main()
