from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_shutdown

from app.application.container import shutdown_container_resources
from app.config import get_settings

settings = get_settings()

celery_app = Celery("orchestrator", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_default_queue="default",
    task_routes={"app.worker.tasks.run_job_task": {"queue": "default"}},
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=settings.job_soft_timeout_seconds,
    task_time_limit=settings.job_hard_timeout_seconds,
    task_track_started=True,
)

if settings.celery_task_always_eager:
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)


@worker_process_shutdown.connect
def _shutdown_worker_resources(**_: object) -> None:
    shutdown_container_resources()
