"""全局配置加载模块：从环境变量构建运行参数并提供缓存访问。"""

from __future__ import annotations

import errno
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv_to_list(value: str) -> list[str]:
    """将逗号分隔字符串转换为去空白列表。"""
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    """系统运行配置对象，从环境变量读取并提供类型化访问。"""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OpenCode Orchestrator"
    api_prefix: str = "/api/v1"
    environment: str = "dev"
    cors_allowed_origins: str = ""
    cors_allowed_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allowed_headers: str = "Authorization,Content-Type,X-Request-Id,X-Client-Platform"
    cors_allow_credentials: bool = False

    database_url: str = "sqlite:///./orchestrator.db"
    redis_url: str = "redis://:AfV(!!=L90@192.168.50.164:6679/0"
    celery_task_always_eager: bool = False

    log_level: str = "INFO"
    log_dir: Path = Field(default=Path("./data/logs"))
    log_format: Literal["json"] = "json"
    log_max_bytes: int = 100 * 1024 * 1024
    log_backup_count: int = 40
    log_debug_modules: str = ""
    log_debug_job_ids: str = ""
    log_redaction_mode: Literal["off", "balanced", "strict"] = "balanced"
    log_payload_preview_chars: int = 256
    log_archive_enabled: bool = True
    log_hot_retention_days: int = 14
    log_cold_retention_days: int = 180
    log_archive_bucket: str | None = None
    log_archive_prefix: str = "orchestrator-logs"
    log_archive_s3_endpoint: str | None = None
    log_archive_region: str = "us-east-1"

    data_root: Path = Field(default=Path("./data/opencode-jobs"))
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

    def cors_allowed_origins_list(self) -> list[str]:
        return _csv_to_list(self.cors_allowed_origins)

    def cors_allowed_methods_list(self) -> list[str]:
        return _csv_to_list(self.cors_allowed_methods)

    def cors_allowed_headers_list(self) -> list[str]:
        return _csv_to_list(self.cors_allowed_headers)

    def log_debug_modules_list(self) -> list[str]:
        return _csv_to_list(self.log_debug_modules)

    def log_debug_job_ids_list(self) -> list[str]:
        return _csv_to_list(self.log_debug_job_ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """构建并缓存 Settings，同时确保数据根目录可写。"""
    settings = Settings()
    if not settings.log_dir.is_absolute():
        settings.log_dir = (Path.cwd() / settings.log_dir).resolve()
    # 相对路径统一按当前工作目录解析，避免不同启动方式下语义漂移。
    if not settings.data_root.is_absolute():
        settings.data_root = (Path.cwd() / settings.data_root).resolve()
    try:
        # 优先使用配置目录；首次启动时自动创建。
        settings.data_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if exc.errno not in {errno.EACCES, errno.EPERM, errno.EROFS}:
            raise
        # 容器只读或权限受限时回退到当前工作目录下的本地路径。
        fallback = (Path.cwd() / "data" / "opencode-jobs").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        settings.data_root = fallback
    return settings
