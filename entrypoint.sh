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

# Create (or update) the default admin when ATIS_ADMIN_EMAIL and
# ATIS_ADMIN_PASSWORD are set.  This lets the first deploy be fully automated.
# create-admin is idempotent (an existing user gets its password updated), so a
# failure here means the admin account is genuinely broken — abort the boot
# (set -e) instead of serving an app that may have no usable admin login.
if [ -n "$ATIS_ADMIN_EMAIL" ] && [ -n "$ATIS_ADMIN_PASSWORD" ]; then
    echo "==> Ensuring admin user exists …"
    flask --app app create-admin \
        --email "$ATIS_ADMIN_EMAIL" \
        --password "$ATIS_ADMIN_PASSWORD" \
        --role Admin
fi

echo "==> Starting gunicorn …"
exec gunicorn --config gunicorn.conf.py app:app
