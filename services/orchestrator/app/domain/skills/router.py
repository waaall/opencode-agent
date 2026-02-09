"""技能路由器：基于需求文本与输入文件特征选择最合适技能。"""

from __future__ import annotations

from pathlib import Path

from app.domain.skills.base import BaseSkill
from app.domain.skills.registry import SkillRegistry


class SkillRouter:
    """技能路由器，根据评分与阈值选出最优技能。"""
    def __init__(self, registry: SkillRegistry, fallback_threshold: float = 0.45) -> None:
        """__init__ 函数实现业务步骤并返回处理结果。
        参数:
        - registry: 业务参数，具体语义见调用上下文。
        - fallback_threshold: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._registry = registry
        self._fallback_threshold = fallback_threshold

    def select(
        self,
        requirement: str,
        files: list[Path],
        skill_code: str | None = None,
    ) -> tuple[BaseSkill, str | None]:
        """选择最终技能；必要时回退到通用技能。
        参数:
        - requirement: 业务参数，具体语义见调用上下文。
        - files: 业务参数，具体语义见调用上下文。
        - skill_code: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if skill_code:
            return self._registry.get(skill_code), None

        scored: list[tuple[float, BaseSkill]] = [
            (skill.score(requirement, files), skill)
            for skill in self._registry.all()
            if skill.code != "general-default"
        ]
        if not scored:
            return self._registry.get("general-default"), "no skill registered, fallback to general-default"

        best_score, best_skill = max(scored, key=lambda item: item[0])
        if best_score < self._fallback_threshold:
            return (
                self._registry.get("general-default"),
                f"max score {best_score:.2f} below threshold {self._fallback_threshold:.2f}",
            )
        return best_skill, None

