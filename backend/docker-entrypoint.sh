#!/usr/bin/env sh
set -e

echo "==> Applying DB migrations (alembic upgrade head)"
python -m alembic upgrade head

if [ "${AUTO_SEED:-true}" != "false" ]; then
    echo "==> Seeding demo data (idempotent — safe to re-run)"
    python scripts/seed_data.py
    python scripts/seed_demo_risk.py
fi

echo "==> Starting gunicorn"
exec gunicorn app.main:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:"${PORT:-8000}" \
    --access-logfile - \
    --error-logfile - \
    --log-level info