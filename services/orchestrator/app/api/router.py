from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.jobs import router as jobs_router
from app.api.v1.skills import router as skills_router

api_router = APIRouter()
api_router.include_router(jobs_router, prefix="/v1", tags=["jobs"])
api_router.include_router(skills_router, prefix="/v1", tags=["skills"])

