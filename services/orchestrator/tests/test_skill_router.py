from pathlib import Path

from app.domain.skills.registry import SkillRegistry
from app.domain.skills.router import SkillRouter


def test_skill_router_manual_override() -> None:
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.45)
    skill, reason = router.select("随便", [Path("foo.txt")], skill_code="ppt")
    assert skill.code == "ppt"
    assert reason is None


def test_skill_router_auto_data_analysis() -> None:
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.45)
    skill, reason = router.select("请基于上传 CSV 做数据分析报告", [Path("sales.csv")], skill_code=None)
    assert skill.code == "data-analysis"
    assert reason is None


def test_skill_router_fallback_when_low_score() -> None:
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.95)
    skill, reason = router.select("just process it", [Path("misc.bin")], skill_code=None)
    assert skill.code == "general-default"
    assert reason is not None

