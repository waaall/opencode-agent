"""技能注册中心：管理技能实例注册、查询与描述信息汇总。"""

from __future__ import annotations

from app.domain.skills.base import BaseSkill
from app.domain.skills.data_analysis import DataAnalysisSkill
from app.domain.skills.general_default import GeneralDefaultSkill
from app.domain.skills.ppt import PptSkill


class SkillRegistry:
    """技能注册中心，统一管理可选技能实例。"""
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self.register(GeneralDefaultSkill())
        self.register(DataAnalysisSkill())
        self.register(PptSkill())

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.code] = skill

    def get(self, skill_code: str) -> BaseSkill:
        """按技能编码获取技能实例。"""
        try:
            return self._skills[skill_code]
        except KeyError as exc:
            raise KeyError(f"unknown skill_code: {skill_code}") from exc

    def all(self) -> list[BaseSkill]:
        return list(self._skills.values())

    def list_descriptors(self) -> list[dict[str, object]]:
        return [skill.descriptor().__dict__ for skill in self._skills.values()]
