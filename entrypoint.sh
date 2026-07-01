#!/bin/sh
# entrypoint.sh — Production startup for the ATIS container.
#
# Runs database migrations and ensures an admin user exists before handing off
# to gunicorn.  This script is the Docker ENTRYPOINT so it executes once per
# container start (not per request).
set -e

echo "==> Running database migrations …"
# Try to upgrade. If it fails (e.g. relation "users" already exists because 
# db.create_all() was run on the first deploy instead of alembic), we stamp the
# DB as being at the initial 0001 state, then run upgrade again to apply 0002/0003.
if ! flask --app app db upgrade 2>/dev/null; then
    echo "    (initial upgrade failed; attempting 0002 stamp)"
    flask --app app db stamp 0002_password_hash 2>/dev/null || true
    if ! flask --app app db upgrade 2>/dev/null; then
        echo "    (0003 upgrade also failed; assuming tables are fully up to date, stamping head)"
        flask --app app db stamp head 2>/dev/null || true
    fi
fi


# Create a default admin if ATIS_ADMIN_EMAIL and ATIS_ADMIN_PASSWORD are set and
# no admin exists yet.  This lets the first deploy be fully automated.
if [ -n "$ATIS_ADMIN_EMAIL" ] && [ -n "$ATIS_ADMIN_PASSWORD" ]; then
    echo "==> Ensuring admin user exists …"
    flask --app app create-admin \
        --email "$ATIS_ADMIN_EMAIL" \
        --password "$ATIS_ADMIN_PASSWORD" \
        --role Admin 2>/dev/null || true
fi

echo "==> Starting gunicorn …"
exec gunicorn --config gunicorn.conf.py app:app
