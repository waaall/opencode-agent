from __future__ import annotations

from functools import lru_cache

from app.application.executor import JobExecutor
from app.application.orchestrator import OrchestratorService
from app.config import Settings, get_settings
from app.domain.skills.registry import SkillRegistry
from app.domain.skills.router import SkillRouter
from app.infra.db.repository import JobRepository
from app.infra.db.session import SessionLocal
from app.infra.opencode.client import OpenCodeClient, OpenCodeCredentials
from app.infra.opencode.event_bridge import OpenCodeEventBridge
from app.infra.security.permission_policy import PermissionPolicyEngine
from app.infra.storage.artifact import ArtifactManager
from app.infra.storage.workspace import WorkspaceManager


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    return SkillRegistry()


@lru_cache(maxsize=1)
def get_repository() -> JobRepository:
    return JobRepository(SessionLocal)


@lru_cache(maxsize=1)
def get_workspace_manager() -> WorkspaceManager:
    settings = get_settings()
    return WorkspaceManager(settings.data_root, settings.max_upload_file_size_bytes)


@lru_cache(maxsize=1)
def get_artifact_manager() -> ArtifactManager:
    return ArtifactManager()


@lru_cache(maxsize=1)
def get_opencode_credentials() -> OpenCodeCredentials:
    settings = get_settings()
    return OpenCodeCredentials(
        username=settings.opencode_server_username,
        password=settings.opencode_server_password,
    )


@lru_cache(maxsize=1)
def get_opencode_client() -> OpenCodeClient:
    settings = get_settings()
    return OpenCodeClient(
        base_url=settings.opencode_base_url,
        credentials=get_opencode_credentials(),
        timeout_seconds=settings.opencode_request_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_event_bridge() -> OpenCodeEventBridge:
    settings = get_settings()
    return OpenCodeEventBridge(
        base_url=settings.opencode_base_url,
        credentials=get_opencode_credentials(),
        timeout_seconds=max(settings.job_soft_timeout_seconds, settings.opencode_request_timeout_seconds),
        stream_read_timeout_seconds=10,
    )


@lru_cache(maxsize=1)
def get_permission_policy() -> PermissionPolicyEngine:
    return PermissionPolicyEngine()


@lru_cache(maxsize=1)
def get_executor() -> JobExecutor:
    settings = get_settings()
    return JobExecutor(
        settings=settings,
        repository=get_repository(),
        skill_registry=get_skill_registry(),
        workspace_manager=get_workspace_manager(),
        artifact_manager=get_artifact_manager(),
        opencode_client=get_opencode_client(),
        event_bridge=get_event_bridge(),
        permission_policy=get_permission_policy(),
    )


@lru_cache(maxsize=1)
def get_orchestrator_service() -> OrchestratorService:
    settings = get_settings()
    return OrchestratorService(
        settings=settings,
        repository=get_repository(),
        skill_registry=get_skill_registry(),
        skill_router=SkillRouter(get_skill_registry(), fallback_threshold=settings.skill_fallback_threshold),
        workspace_manager=get_workspace_manager(),
        artifact_manager=get_artifact_manager(),
        opencode_client=get_opencode_client(),
    )


def shutdown_container_resources() -> None:
    if get_opencode_client.cache_info().currsize:
        try:
            get_opencode_client().close()
        except Exception:
            pass
    if get_event_bridge.cache_info().currsize:
        try:
            get_event_bridge().close()
        except Exception:
            pass

    for provider in (
        get_executor,
        get_orchestrator_service,
        get_event_bridge,
        get_opencode_client,
        get_opencode_credentials,
        get_permission_policy,
        get_artifact_manager,
        get_workspace_manager,
        get_repository,
        get_skill_registry,
    ):
        provider.cache_clear()
