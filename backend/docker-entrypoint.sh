#!/bin/sh
set -e

python -m app.db.migrate_bootstrap
alembic upgrade head
python -m app.seed

exec "$@"
