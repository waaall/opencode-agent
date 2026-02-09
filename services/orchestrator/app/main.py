"""FastAPI 应用入口：初始化生命周期、中间件、健康检查与路由挂载。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.application.container import shutdown_container_resources
from app.config import get_settings
from app.infra.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动建表，关闭释放依赖资源。"""
    # 服务启动时确保表结构存在，避免首个请求触发表缺失错误。
    init_db()
    try:
        yield
    finally:
        shutdown_container_resources()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

if settings.cors_allowed_origins_list():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list(),
        allow_methods=settings.cors_allowed_methods_list(),
        allow_headers=settings.cors_allowed_headers_list(),
        allow_credentials=settings.cors_allow_credentials,
    )


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    """透传或生成 X-Request-Id，并回写到响应头。"""
    # 优先透传上游网关的请求 ID；不存在时本地生成，便于全链路定位问题。
    request_id = request.headers.get("X-Request-Id") or str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
