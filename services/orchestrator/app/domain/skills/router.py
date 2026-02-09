"""技能路由器：基于需求文本与输入文件特征选择最合适技能。"""

from __future__ import annotations

from pathlib import Path

from app.domain.skills.base import BaseSkill
from app.domain.skills.registry import SkillRegistry


class SkillRouter:
    """技能路由器，根据评分与阈值选出最优技能。"""
    def __init__(self, registry: SkillRegistry, fallback_threshold: float = 0.45) -> None:
        self._registry = registry
        self._fallback_threshold = fallback_threshold

    def select(
        self,
        requirement: str,
        files: list[Path],
        skill_code: str | None = None,
    ) -> tuple[BaseSkill, str | None]:
        """选择最终技能；低于阈值时回退到通用技能。"""
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
