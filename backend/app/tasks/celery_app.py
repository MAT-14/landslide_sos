from celery import Celery

from app.config import settings

celery_app = Celery(
    "landslidesos",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "recompute-risk-30min": {
            "task": "risk.recompute_all",
            "schedule": float(settings.CELERY_RECONCILE_MINUTES) * 60.0,
        },
        "ingest-imd-rainfall-60min": {
            "task": "rainfall.ingest_imd",
            "schedule": 3600.0,
        },
    },
)

# Import task modules so their names are registered on this app.
from app.tasks import rainfall_tasks  # noqa: E402,F401
from app.tasks import risk_tasks  # noqa: E402,F401
from app.tasks import alert_tasks  # noqa: E402,F401