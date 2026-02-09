"""技能路由测试：验证手动覆盖、自动识别与低分兜底分支。"""

from pathlib import Path

from app.domain.skills.registry import SkillRegistry
from app.domain.skills.router import SkillRouter


def test_skill_router_manual_override() -> None:
    """验证手动指定技能时应直接命中对应技能。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.45)
    skill, reason = router.select("随便", [Path("foo.txt")], skill_code="ppt")
    assert skill.code == "ppt"
    assert reason is None


def test_skill_router_auto_data_analysis() -> None:
    """验证数据分析场景可自动路由到 data-analysis。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.45)
    skill, reason = router.select("请基于上传 CSV 做数据分析报告", [Path("sales.csv")], skill_code=None)
    assert skill.code == "data-analysis"
    assert reason is None


def test_skill_router_fallback_when_low_score() -> None:
    """验证评分过低时回退到通用技能。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    registry = SkillRegistry()
    router = SkillRouter(registry, fallback_threshold=0.95)
    skill, reason = router.select("just process it", [Path("misc.bin")], skill_code=None)
    assert skill.code == "general-default"
    assert reason is not None

