#!/bin/sh
# entrypoint.sh — Production startup for the ATIS container.
#
# Runs database migrations and ensures an admin user exists before handing off
# to gunicorn.  This script is the Docker ENTRYPOINT so it executes once per
# container start (not per request).
set -e

echo "==> Running database migrations …"
flask --app app db upgrade

if [ "$ATIS_SEED_DEMO" = "1" ] || [ "$ATIS_SEED_DEMO" = "true" ]; then
    echo "==> Ensuring demo users exist …"
    flask --app app seed-demo-users
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
