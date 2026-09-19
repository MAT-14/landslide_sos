"""Vercel serverless entrypoint for the LandslideSOS FastAPI backend.

The FastAPI app lives in backend/app. Vercel loads whatever is named ``app``
here as the ASGI application and routes every request to it, so the full
``/api/v1/*`` surface works (see ``vercel.json`` rewrites).

Env vars (set in the Vercel project dashboard, never committed):
    DATABASE_URL           Neon pooled Postgres URL (?sslmode=require)
    SECRET_KEY             random 64-char hex
    ENVIRONMENT            production
    DEBUG                  false
    AUTO_CREATE_TABLES     false   (schema is created by DB bootstrap below)
    AUTO_MIGRATE           true    (optional; set "false" to skip bootstrap)
    CORS_ALLOW_ALL         false
    CORS_ORIGINS           ["https://landslide-sos.vercel.app"]
    SMS_PROVIDER           msg91   (empty MSG91_AUTH_KEY => simulation)
"""

import logging
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, _BACKEND_DIR)

logger = logging.getLogger("vercel.bootstrap")


def _bootstrap_db() -> None:
    """Provision the Postgres schema once, so no Shell is needed on Vercel.

    Mirrors backend/docker-entrypoint.sh: run alembic migrations, then the two
    idempotent demo seeders. Runs only when the DB has never been migrated, so
    every later cold start (and every instance) is a fast no-op.
    """
    if os.getenv("AUTO_MIGRATE", "true").lower() == "false":
        logger.info("AUTO_MIGRATE=false — skipping schema/seed bootstrap")
        return

    from sqlalchemy import inspect

    from app.config import settings  # noqa: F401  (ensures env vars resolve early)
    from app.database import engine

    if "alembic_version" in inspect(engine).get_table_names():
        logger.info("DB already migrated — skipping bootstrap")
        return

    import alembic.command
    import alembic.config

    cfg = alembic.config.Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))

    logger.info("Applying DB migrations (alembic upgrade head)")
    alembic.command.upgrade(cfg, "head")

    sys.path.insert(0, os.path.join(_BACKEND_DIR, "scripts"))
    import seed_data
    import seed_demo_risk

    logger.info("Seeding demo data (idempotent)")
    seed_data.seed()
    seed_demo_risk.seed(reset_alerts=False, dispatch_sms=False, reset_reports=False)
    logger.info("DB bootstrap complete")


try:
    _bootstrap_db()
except Exception:  # never crash the function; the app still starts and logs the error
    logging.getLogger("vercel.bootstrap").exception("DB bootstrap failed")

from app.main import app  # noqa: E402