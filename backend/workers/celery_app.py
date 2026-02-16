from celery import Celery
from celery.schedules import schedule
from kombu import Queue

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
    task_default_queue="publishing",
    task_queues=(
        Queue("publishing"),
        Queue("scheduler"),
        Queue("analytics"),
    ),
    task_routes={
        "workers.tasks.publish_post": {"queue": "publishing"},
        "workers.tasks.schedule_due_posts": {"queue": "scheduler"},
        "workers.tasks.schedule_due_automation_rules": {"queue": "scheduler"},
        "workers.tasks.process_publish_event_rules": {"queue": "scheduler"},
        "workers.tasks.worker_heartbeat": {"queue": "scheduler"},
        "workers.tasks.analytics_*": {"queue": "analytics"},
    },
    beat_schedule={
        "publish-scheduler-every-30s": {
            "task": "workers.tasks.schedule_due_posts",
            "schedule": schedule(30.0),
            "options": {"queue": "scheduler"},
        },
        "automation-scheduler-every-30s": {
            "task": "workers.tasks.schedule_due_automation_rules",
            "schedule": schedule(30.0),
            "options": {"queue": "scheduler"},
        },
        "automation-event-rules-every-20s": {
            "task": "workers.tasks.process_publish_event_rules",
            "schedule": schedule(20.0),
            "options": {"queue": "scheduler"},
        },
        "worker-heartbeat-every-15s": {
            "task": "workers.tasks.worker_heartbeat",
            "schedule": schedule(15.0),
            "options": {"queue": "scheduler"},
        },
        "billing-reset-monthly-usage-daily": {
            "task": "workers.tasks.reset_monthly_post_usage",
            "schedule": schedule(86400.0),
            "options": {"queue": "scheduler"},
        },
    },
)

celery_app.autodiscover_tasks(["workers"])
