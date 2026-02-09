"""异步任务定义：执行作业并对网络异常执行退避重试。"""

from __future__ import annotations

import httpx

from app.application.container import get_executor
from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="app.worker.tasks.run_job_task")
def run_job_task(self, job_id: str) -> None:
    """Celery 任务入口，执行作业并处理网络失败重试。
    参数:
    - job_id: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    executor = get_executor()
    try:
        executor.run(job_id)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        # 首次快速重试，后续拉长退避，兼顾瞬时抖动与雪崩风险。
        countdown = 30 if self.request.retries == 0 else 120
        raise self.retry(exc=exc, max_retries=2, countdown=countdown)
