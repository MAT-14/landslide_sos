"""Vercel serverless entrypoint for the LandslideSOS FastAPI backend.

The FastAPI app lives in backend/app. Vercel loads whatever is named ``app``
here as the ASGI application and routes every request to it, so the full
``/api/v1/*`` surface works (see ``vercel.json`` rewrites).

Env vars (set in the Vercel project dashboard, never committed):
    DATABASE_URL           Neon pooled Postgres URL (?sslmode=require)
    SECRET_KEY             random 64-char hex
    ENVIRONMENT            production
    DEBUG                  false
    AUTO_CREATE_TABLES     false   (schema is created via alembic, see DEPLOY.md)
    CORS_ALLOW_ALL         false
    CORS_ORIGINS           ["https://landslide-sos.vercel.app"]
    SMS_PROVIDER           msg91   (empty MSG91_AUTH_KEY => simulation)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.main import app  # noqa: E402