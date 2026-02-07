from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OpenCode Orchestrator"
    api_prefix: str = "/api/v1"
    environment: str = "dev"

    database_url: str = "sqlite:///./orchestrator.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    data_root: Path = Field(default=Path("/data/opencode-jobs"))
    workspace_retention_hours: int = 72

    opencode_base_url: str = "http://127.0.0.1:4096"
    opencode_server_username: str = "opencode"
    opencode_server_password: str | None = None
    opencode_request_timeout_seconds: int = 30

    default_agent: str = "build"
    skill_fallback_threshold: float = 0.45
    max_upload_file_size_bytes: int = 50 * 1024 * 1024
    permission_wait_timeout_seconds: int = 120
    job_soft_timeout_seconds: int = 15 * 60
    job_hard_timeout_seconds: int = 20 * 60

    # Single tenant for v1, but schema is multi-tenant ready.
    default_tenant_id: str = "default"
    default_created_by: str = "system"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    try:
        settings.data_root.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = (Path.cwd() / "data" / "opencode-jobs").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        settings.data_root = fallback
    return settings
