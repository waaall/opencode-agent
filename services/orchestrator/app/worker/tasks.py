"""异步任务定义：执行作业并对网络异常执行退避重试。"""

from __future__ import annotations

import logging

import httpx

from app.application.container import get_executor
from app.config import get_settings
from app.infra.logging.context import bind_log_context
from app.worker.log_archive import archive_logs_once
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.worker.tasks.run_job_task")
def run_job_task(self, job_id: str) -> None:
    """执行作业任务，网络错误时按退避策略重试。"""
    with bind_log_context(job_id=job_id, task_id=self.request.id):
        logger.info(
            "worker task started",
            extra={
                "event": "job.task.started",
                "retry": self.request.retries,
                "payload_preview": {"job_id": job_id},
            },
        )
        executor = get_executor()
        try:
            executor.run(job_id)
            logger.info("worker task finished", extra={"event": "job.task.succeeded"})
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            # 首次快速重试，后续拉长退避，兼顾瞬时抖动与雪崩风险。
            countdown = 30 if self.request.retries == 0 else 120
            logger.warning(
                "worker task transient network error",
                extra={
                    "event": "job.task.retrying",
                    "retry": self.request.retries,
                    "external_service": "opencode",
                    "op": "executor.run",
                    "payload_preview": {"countdown": countdown},
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise self.retry(exc=exc, max_retries=2, countdown=countdown)
        except Exception as exc:
            logger.exception(
                "worker task failed",
                extra={"event": "job.task.failed", "error_type": type(exc).__name__, "error": str(exc)},
            )
            raise


@celery_app.task(bind=True, name="app.worker.tasks.archive_logs_task")
def archive_logs_task(self) -> None:
    """归档日志切片到对象存储，并执行保留清理。"""
    settings = get_settings()
    with bind_log_context(task_id=self.request.id):
        logger.info("log archive task started", extra={"event": "log.archive.task.started"})
        summary = archive_logs_once(settings=settings)
        logger.info(
            "log archive task finished",
            extra={"event": "log.archive.task.succeeded", "payload_preview": summary},
        )
