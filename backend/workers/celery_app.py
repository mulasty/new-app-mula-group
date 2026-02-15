from celery import Celery
from celery.schedules import schedule

from app.core.config import settings

celery_app = Celery(
    "control_center",
    broker=settings.cache_redis_url,
    backend=settings.cache_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "publish-scheduler-every-30s": {
            "task": "workers.tasks.schedule_due_posts",
            "schedule": schedule(30.0),
        }
    },
)

celery_app.autodiscover_tasks(["workers"])
