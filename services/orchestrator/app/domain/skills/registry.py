"""技能注册中心：管理技能实例注册、查询与描述信息汇总。"""

from __future__ import annotations

from app.domain.skills.base import BaseSkill
from app.domain.skills.data_analysis import DataAnalysisSkill
from app.domain.skills.general_default import GeneralDefaultSkill
from app.domain.skills.ppt import PptSkill


class SkillRegistry:
    """技能注册中心，统一管理可选技能实例。"""
    def __init__(self) -> None:
        """__init__ 函数实现业务步骤并返回处理结果。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._skills: dict[str, BaseSkill] = {}
        self.register(GeneralDefaultSkill())
        self.register(DataAnalysisSkill())
        self.register(PptSkill())

    def register(self, skill: BaseSkill) -> None:
        """注册技能实例到注册中心。
        参数:
        - skill: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._skills[skill.code] = skill

    def get(self, skill_code: str) -> BaseSkill:
        """按技能编码获取技能实例。
        参数:
        - skill_code: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        try:
            return self._skills[skill_code]
        except KeyError as exc:
            raise KeyError(f"unknown skill_code: {skill_code}") from exc

    def all(self) -> list[BaseSkill]:
        """返回全部已注册技能实例。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return list(self._skills.values())

    def list_descriptors(self) -> list[dict[str, object]]:
        """返回全部技能描述信息。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return [skill.descriptor().__dict__ for skill in self._skills.values()]

