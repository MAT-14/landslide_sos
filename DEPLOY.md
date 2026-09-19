# LandslideSOS — Deployment Guide

## Prerequisites

- Docker 24+ and Docker Compose v2
- 4 GB RAM minimum (Postgres + PostGIS + backend + Celery)
- Port 8000 (API), 5432 (Postgres), 6379 (Redis) available

## Quick Start (Docker Compose)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/landslide-sos.git
cd landslide-sos

# 2. Create a .env file (copy the example)
cp backend/.env.example .env

# 3. Edit .env — set at minimum:
#    SECRET_KEY=<random 64-char string>
#    ENVIRONMENT=production
#    DEBUG=false
#    AUTO_CREATE_TABLES=false

# 4. Generate a secret key
python -c "import secrets; print(secrets.token_hex(32))"

# 5. Start all services
docker compose up -d

# 6. Run database migrations
docker compose exec backend python -m alembic upgrade head

# 7. Seed initial data (dev only)
docker compose exec backend python scripts/seed_data.py
docker compose exec backend python scripts/load_inventory.py
docker compose exec backend python scripts/compute_swi.py

# 8. Train the risk model
docker compose exec backend python scripts/train_model.py

# 9. Verify
curl http://localhost:8000/api/v1/system/health
```

## Architecture (Docker)

| Service | Port | Purpose |
|---------|------|---------|
| `backend` | 8000 | FastAPI + Gunicorn (4 workers, Uvicorn) |
| `celery-worker` | — | Task execution (SMS, risk scoring) |
| `celery-beat` | — | Scheduled tasks (risk recompute 30min, rainfall 60min) |
| `postgres` | 5432 | PostGIS-enabled primary database |
| `redis` | 6379 | Celery broker + result backend |

## Environment Variables

### Required for Production

| Variable | Example | Notes |
|----------|---------|-------|
| `SECRET_KEY` | `<random-hex-64>` | **Must** differ from dev default |
| `ENVIRONMENT` | `production` | Triggers security validation on startup |
| `DEBUG` | `false` | Disables Swagger docs, verbose logging |
| `AUTO_CREATE_TABLES` | `false` | Use `alembic upgrade head` instead |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostGIS connection string |

### Optional (Feature-Specific)

| Variable | Default | Notes |
|----------|---------|-------|
| `SMS_PROVIDER` | `mock` | Set to `msg91` for live SMS |
| `MSG91_AUTH_KEY` | — | From msg91.com dashboard |
| `IMD_API_KEY` | — | IP-whitelisted at api.imd.gov.in |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Production uses Redis |
| `DB_POOL_SIZE` | `5` | Postgres connection pool size |

## Database (PostgreSQL + PostGIS)

The production database uses PostGIS for spatial queries. The schema uses
`geom_wkt` (WKT text) as the SQLite-safe geospatial carrier; on Postgres
you can migrate to GeoAlchemy2 `Geometry(Point, 4326)` columns.

```bash
# Backup
docker compose exec postgres pg_dump -U landslidesos landslidesos > backup.sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U landslidesos landslidesos
```

## Celery Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `risk.recompute_all` | Every 30 min | Recompute SWI + fused risk for all zones |
| `rainfall.ingest_imd` | Every 60 min | Fetch latest IMD rainfall data |
| `alert.dispatch_sms` | On-demand | Send SMS for a single alert |
| `alert.dispatch_sms_batch` | On-demand | Send SMS to pre-resolved phone list |

```bash
# Check worker health
docker compose exec celery-worker celery -A app.tasks.celery_app inspect ping

# Manually trigger risk recompute
docker compose exec celery-worker celery -A app.tasks.celery_app call risk.recompute_all
```

## Monitoring

- **API health:** `GET /api/v1/system/health` — reports all component statuses
- **Structured logs:** Every request gets `X-Request-ID` (returned in response header)
- **Logs:** `docker compose logs -f backend` (or `celery-worker`, `celery-beat`)

## Scaling

```bash
# Scale backend (add more API workers)
docker compose up -d --scale backend=3

# Scale Celery workers
docker compose up -d --scale celery-worker=2
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `SECRET_KEY` error on startup | Generate a new key: `python -c "import secrets; print(secrets.token_hex(32))"` |
| Celery worker won't connect | Check Redis: `docker compose exec redis redis-cli ping` |
| Postgres connection refused | Check container: `docker compose ps postgres` |
| Model not found | Train first: `docker compose exec backend python scripts/train_model.py` |
| SMS not sending | Check `SMS_PROVIDER` in `.env`; `mock` logs to console |

## Hosting on Render (managed)

The repo ships a `render.yaml` Blueprint so the backend can run as a hosted
service (used by the Vercel-deployed frontend).

One-time deploy:
1. Push the repo to GitHub (backend.Dockerfile + `render.yaml` must be present).
2. Render Dashboard → **New +** → **Blueprint** → connect the repo.
3. Render creates two resources:
   - `landslideos-db` — managed PostgreSQL (free tier).
   - `landslideos-api` — web service (Docker → gunicorn), `PORT` handled by Render.
4. Wait for the web service to deploy. On container startup it runs
   `python -m alembic upgrade head` and — unless `AUTO_SEED=false` — the
   idempotent demo seed (`scripts/seed_data.py` + `scripts/seed_demo_risk.py`),
   so no Shell access is required. Check the service logs for
   "Applying DB migrations" / "Seeding demo data".
5. Note the web-service URL, e.g. `https://landslideos-api.onrender.com`.

Point the Vercel frontend at it:
- Vercel project → **Settings → Environment Variables** → add
  `VITE_API_BASE = <your-render-url>/api/v1` (production) → **Redeploy**.
- Or run locally: `$env:VITE_API_BASE="<render-url>/api/v1"; npm run dev`.

Demo-login credentials (seeded): `admin@landslidesos.in` / `admin123456` and
`officer@landslidesos.in` / `officer123456`.

Demo-safe defaults on Render (override in service env vars to use real data):
| Setting | Default | Live override |
|---------|---------|---------------|
| `SMS_PROVIDER` / `MSG91_AUTH_KEY` | `msg91` / empty → simulation | your msg91 key |
| `IMD_API_KEY` | empty → simulated SIM-* readings | whitelisted IMD key |
| `OPENTOPOGRAPHY_API_KEY` | empty | your OT key |
| `CELERY_TASK_ALWAYS_EAGER` | `true` → tasks run inline (enforced in `celery_app.py`) | run a worker + Redis |
| `CORS_ORIGINS` | localhost + `https://landslide-sos.vercel.app` | your frontend origin(s) |

Free-tier caveats:
- The web service **sleeps after ~15 min idle**; the first request after idle
  takes ~30–60 s to wake.
- Free Postgres has storage/hard limits and older free instances expire after
  90 days. For a longer-lived demo, add a Neon/Supabase connection string via
  `DATABASE_URL` instead.
- Render's random JWT `SECRET_KEY` is generated once at deploy (`generateValue`);
  changing it invalidates existing login tokens.
