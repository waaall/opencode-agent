"""API 总路由配置，按业务域注册 jobs 与 skills 子路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.jobs import router as jobs_router
from app.api.v1.skills import router as skills_router
from app.config import get_settings

settings = get_settings()

api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(jobs_router, tags=["jobs"])
api_router.include_router(skills_router, tags=["skills"])
