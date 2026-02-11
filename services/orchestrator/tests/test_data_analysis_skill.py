"""data-analysis 技能测试：验证运行时配置生成与执行计划约束。"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.models import JobContext
from app.domain.skills.data_analysis import DataAnalysisSkill


def _build_ctx(workspace_dir: Path) -> JobContext:
    return JobContext(
        job_id="job-1",
        tenant_id="default",
        requirement="analyze",
        workspace_dir=workspace_dir,
        input_files=[workspace_dir / "inputs" / "raw.csv"],
        selected_skill="data-analysis",
        agent="build",
        model=None,
        output_contract=None,
    )


def test_data_analysis_prepare_workspace_generates_runtime_config(tmp_path: Path) -> None:
    """应在 job 目录生成 data-analysis 运行配置，并固定写入 outputs。"""
    workspace = tmp_path / "job-1"
    (workspace / "inputs").mkdir(parents=True, exist_ok=True)
    ctx = _build_ctx(workspace)
    skill = DataAnalysisSkill()
    plan = skill.build_execution_plan(ctx)

    skill.prepare_workspace(ctx, plan)

    config_path = workspace / "job" / "data-analysis.config.json"
    assert config_path.exists()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["workspace_root"] == str(workspace.resolve())
    assert payload["input_path"] == str((workspace / "inputs").resolve())
    assert payload["output_dir"] == str((workspace / "outputs").resolve())
    assert payload["allow_external_paths"] is False
    assert payload["fallback_to_temp_output"] is False
    assert payload["analysis_mode"] == "combined"


def test_data_analysis_execution_plan_contains_runtime_config_path(tmp_path: Path) -> None:
    """执行计划应明确声明运行时配置文件路径。"""
    ctx = _build_ctx(tmp_path / "job-2")
    skill = DataAnalysisSkill()

    plan = skill.build_execution_plan(ctx)

    assert plan["runtime"]["config_path"] == "job/data-analysis.config.json"
    assert plan["runtime"]["output_dir"] == "outputs"
