"""技能目录接口：列出可用技能并查询指定技能的元数据。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas import SkillResponse
from app.application.container import get_orchestrator_service
from app.application.orchestrator import OrchestratorService

router = APIRouter()


def _service() -> OrchestratorService:
    """依赖注入辅助函数，返回编排服务实例。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return get_orchestrator_service()


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(
    task_type: str | None = None,
    orchestrator: OrchestratorService = Depends(_service),
) -> list[SkillResponse]:
    """按可选任务类型过滤并返回技能列表。
    参数:
    - task_type: 业务参数，具体语义见调用上下文。
    - orchestrator: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return [SkillResponse(**item) for item in orchestrator.list_skills(task_type=task_type)]


@router.get("/skills/{skill_code}", response_model=SkillResponse)
def get_skill(
    skill_code: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> SkillResponse:
    """返回指定技能的详细元数据。
    参数:
    - skill_code: 业务参数，具体语义见调用上下文。
    - orchestrator: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    try:
        return SkillResponse(**orchestrator.get_skill(skill_code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

