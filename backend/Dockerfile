FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev libgomp1 gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

FROM base AS production

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    mkdir -p /app/data /app/models && \
    chown -R app:app /app && \
    chmod +x /app/docker-entrypoint.sh

ENV HOME=/app

USER app

EXPOSE 8000

# Runs alembic migrations (+ idempotent demo seed unless AUTO_SEED=false),
# then starts gunicorn. No manual shell needed on Render.
CMD ["./docker-entrypoint.sh"]
