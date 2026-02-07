from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.application.container import shutdown_container_resources
from app.config import get_settings
from app.infra.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    try:
        yield
    finally:
        shutdown_container_resources()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
