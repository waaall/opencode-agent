"""依赖容器模块，负责单例化创建仓储、客户端与应用服务对象。"""

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
    """获取技能注册中心单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return SkillRegistry()


@lru_cache(maxsize=1)
def get_repository() -> JobRepository:
    """获取作业仓储单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return JobRepository(SessionLocal)


@lru_cache(maxsize=1)
def get_workspace_manager() -> WorkspaceManager:
    """获取工作区管理器单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    settings = get_settings()
    # 工作区管理器依赖上传大小阈值，避免 API 层与存储层规则不一致。
    return WorkspaceManager(settings.data_root, settings.max_upload_file_size_bytes)


@lru_cache(maxsize=1)
def get_artifact_manager() -> ArtifactManager:
    """获取产物管理器单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return ArtifactManager()


@lru_cache(maxsize=1)
def get_opencode_credentials() -> OpenCodeCredentials:
    """获取 OpenCode 认证信息单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    settings = get_settings()
    return OpenCodeCredentials(
        username=settings.opencode_server_username,
        password=settings.opencode_server_password,
    )


@lru_cache(maxsize=1)
def get_opencode_client() -> OpenCodeClient:
    """获取 OpenCode 客户端单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    settings = get_settings()
    return OpenCodeClient(
        base_url=settings.opencode_base_url,
        credentials=get_opencode_credentials(),
        timeout_seconds=settings.opencode_request_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_event_bridge() -> OpenCodeEventBridge:
    """获取 OpenCode 事件桥接器单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    settings = get_settings()
    return OpenCodeEventBridge(
        base_url=settings.opencode_base_url,
        credentials=get_opencode_credentials(),
        # 桥接超时至少覆盖作业软超时，避免长任务中途断流。
        timeout_seconds=max(settings.job_soft_timeout_seconds, settings.opencode_request_timeout_seconds),
        stream_read_timeout_seconds=10,
    )


@lru_cache(maxsize=1)
def get_permission_policy() -> PermissionPolicyEngine:
    """获取权限策略引擎单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return PermissionPolicyEngine()


@lru_cache(maxsize=1)
def get_executor() -> JobExecutor:
    """获取作业执行器单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
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
    """获取编排服务单例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
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
    """关闭共享客户端并清理依赖容器缓存。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
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

    # 按依赖顺序清理缓存，确保后续请求可重新构建全新实例。
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
