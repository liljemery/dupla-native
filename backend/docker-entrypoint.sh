#!/bin/sh
set -e

python -m app.db.migrate_bootstrap
alembic upgrade heads
python -m app.seed

exec "$@"
