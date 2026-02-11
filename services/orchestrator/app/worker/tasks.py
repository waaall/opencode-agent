"""异步任务定义：执行作业并对网络异常执行退避重试。"""

from __future__ import annotations

import logging

import httpx

from app.application.container import get_executor
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.worker.tasks.run_job_task")
def run_job_task(self, job_id: str) -> None:
    """执行作业任务，网络错误时按退避策略重试。"""
    logger.info("run_job_task started: job_id=%s retry=%s", job_id, self.request.retries)
    executor = get_executor()
    try:
        executor.run(job_id)
        logger.info("run_job_task finished: job_id=%s", job_id)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        # 首次快速重试，后续拉长退避，兼顾瞬时抖动与雪崩风险。
        countdown = 30 if self.request.retries == 0 else 120
        logger.warning(
            "run_job_task transient network error: job_id=%s retry=%s countdown=%s error=%s",
            job_id,
            self.request.retries,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, max_retries=2, countdown=countdown)
