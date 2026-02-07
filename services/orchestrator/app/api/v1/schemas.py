from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    selected_skill: str


class JobStartResponse(BaseModel):
    job_id: str
    status: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: str
    session_id: str | None
    selected_skill: str
    agent: str
    model: dict[str, str] | None
    error_code: str | None
    error_message: str | None
    download_url: str | None
    created_at: datetime
    updated_at: datetime


class ArtifactItem(BaseModel):
    id: int
    category: str
    relative_path: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    created_at: datetime


class ArtifactListResponse(BaseModel):
    job_id: str
    artifacts: list[ArtifactItem]
    bundle_ready: bool


class SkillResponse(BaseModel):
    code: str
    name: str
    aliases: tuple[str, ...]
    version: str
    schema_version: str
    description: str
    task_type: str
    sample_output_contract: dict[str, Any] | None = None
