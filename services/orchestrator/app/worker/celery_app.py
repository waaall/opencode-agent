"""Celery 应用配置：定义队列路由、超时策略与关闭资源回收。"""

from __future__ import annotations

import logging
import sys

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_shutdown

from app.application.container import shutdown_container_resources
from app.config import get_settings
from app.infra.logging.setup import configure_logging, shutdown_logging

settings = get_settings()


def _detect_process_role() -> str | None:
    argv = " ".join(sys.argv[1:]).lower()
    if "beat" in argv:
        return "beat"
    if "worker" in argv:
        return "worker"
    return None


process_role = _detect_process_role()
logger = logging.getLogger(__name__)
if process_role:
    configure_logging(settings, process_role=process_role)

celery_app = Celery("orchestrator", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    imports=("app.worker.tasks",),
    task_default_queue="default",
    task_routes={
        "app.worker.tasks.run_job_task": {"queue": "default"},
        "app.worker.tasks.archive_logs_task": {"queue": "default"},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=settings.job_soft_timeout_seconds,
    task_time_limit=settings.job_hard_timeout_seconds,
    task_track_started=True,
)

if settings.celery_task_always_eager:
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

if settings.log_archive_enabled:
    celery_app.conf.beat_schedule = {
        **dict(celery_app.conf.beat_schedule or {}),
        "archive-logs-daily": {
            "task": "app.worker.tasks.archive_logs_task",
            "schedule": crontab(minute=15, hour=1),
        },
    }

if process_role:
    logger.info(
        "celery app configured",
        extra={
            "event": "celery.config.loaded",
            "external_service": "redis",
            "op": process_role,
            "payload_preview": {
                "broker": settings.redis_url,
                "always_eager": settings.celery_task_always_eager,
                "log_archive_enabled": settings.log_archive_enabled,
            },
        },
    )


@worker_process_shutdown.connect
def _shutdown_worker_resources(**_: object) -> None:
    """Worker 进程关闭时释放共享资源。"""
    shutdown_container_resources()
    shutdown_logging()
