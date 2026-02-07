from __future__ import annotations

import httpx

from app.application.container import get_executor
from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="app.worker.tasks.run_job_task")
def run_job_task(self, job_id: str) -> None:
    executor = get_executor()
    try:
        executor.run(job_id)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        countdown = 30 if self.request.retries == 0 else 120
        raise self.retry(exc=exc, max_retries=2, countdown=countdown)

