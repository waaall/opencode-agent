"""数据分析技能实现：识别分析任务并生成分析型执行约束。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.models import JobContext
from app.domain.skills.base import BaseSkill


class DataAnalysisSkill(BaseSkill):
    """数据分析技能实现，面向结构化数据分析与报表输出。"""
    code = "data-analysis"
    name = "Data Analysis"
    aliases = ("analysis", "csv-analysis")
    version = "1.0.0"
    schema_version = "1.0.0"
    description = "Analyze tabular data and output report with charts."
    task_type = "data_analysis"

    DATA_KEYWORDS = (
        "数据",
        "分析",
        "统计",
        "报表",
        "趋势",
        "csv",
        "excel",
        "dataset",
        "analyze",
    )
    DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".json"}

    def score(self, requirement: str, files: list[Path]) -> float:
        """基于关键词和文件后缀为数据分析任务打分。"""
        text = requirement.lower()
        keyword_hits = sum(1 for keyword in self.DATA_KEYWORDS if keyword in text)
        file_hits = sum(1 for path in files if path.suffix.lower() in self.DATA_EXTENSIONS)
        score = 0.15 + keyword_hits * 0.12 + file_hits * 0.2
        return min(1.0, score)

    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """构建数据分析技能的执行计划。"""
        default_contract: dict[str, Any] = {
            "required_files": ["report.md"],
            "suggested_files": ["charts/overview.png"],
        }
        merged_contract = default_contract if ctx.output_contract is None else ctx.output_contract
        return {
            "schema_version": self.schema_version,
            "selected_skill": self.code,
            "output_contract": merged_contract,
            "packaging_rules": {"include": ["outputs/**", "job/request.md", "job/execution-plan.json"]},
            "timeouts": {"soft_seconds": 15 * 60, "hard_seconds": 20 * 60},
            "retry_policy": {"max_attempts": 2, "backoff_seconds": [30, 120]},
            "analysis_rules": {
                "language": "zh-CN",
                "chart_engine": "matplotlib",
                "write_assumptions_to_readme": True,
            },
        }

    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """生成面向数据分析执行的 prompt。"""
        return (
            "请执行 data-analysis skill 完成数据分析任务。\n"
            "硬性要求:\n"
            "- 从 inputs/ 读取原始数据，不修改原始文件\n"
            "- 在 outputs/report.md 输出结构化分析结论\n"
            "- 在 outputs/charts/ 生成可复现实验图表（优先 png）\n"
            "- 若字段含义不完整，做最小合理假设并写入 outputs/README.md\n"
            "- 严格按照 execution-plan.json 的 output_contract 验收目标执行\n\n"
            "execution-plan.json:\n"
            f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n"
        )

    def validate_outputs(self, ctx: JobContext) -> None:
        """校验数据分析技能输出是否满足契约。"""
        outputs_dir = ctx.workspace_dir / "outputs"
        report = outputs_dir / "report.md"
        if not report.exists():
            raise ValueError("data-analysis requires outputs/report.md")
        required_files = self._required_files_from_contract(ctx.output_contract)
        for required in required_files:
            if not (outputs_dir / required).exists():
                raise ValueError(f"missing required output file: {required}")

    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """返回数据分析技能产物清单。"""
        return [
            {"kind": "report", "path": "outputs/report.md"},
            {"kind": "chart_dir", "path": "outputs/charts"},
        ]
