from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas import SkillResponse
from app.application.container import get_orchestrator_service
from app.application.orchestrator import OrchestratorService

router = APIRouter()


def _service() -> OrchestratorService:
    return get_orchestrator_service()


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(
    task_type: str | None = None,
    orchestrator: OrchestratorService = Depends(_service),
) -> list[SkillResponse]:
    return [SkillResponse(**item) for item in orchestrator.list_skills(task_type=task_type)]


@router.get("/skills/{skill_code}", response_model=SkillResponse)
def get_skill(
    skill_code: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> SkillResponse:
    try:
        return SkillResponse(**orchestrator.get_skill(skill_code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

