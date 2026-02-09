"""通用兜底技能实现：当路由置信度不足时提供保底执行策略。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.models import JobContext
from app.domain.skills.base import BaseSkill


class GeneralDefaultSkill(BaseSkill):
    """通用兜底技能实现，处理无法明确归类的任务请求。"""
    code = "general-default"
    name = "General Default"
    aliases = ("auto", "general")
    version = "1.0.0"
    schema_version = "1.0.0"
    description = "Generic fallback skill for unmatched requirements."
    task_type = "general"

    def score(self, requirement: str, files: list[Path]) -> float:
        """根据需求与输入文件计算技能匹配分数。
        参数:
        - requirement: 业务参数，具体语义见调用上下文。
        - files: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if not requirement.strip():
            return 0.2
        return 0.5

    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """构建当前技能的执行计划数据结构。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        required_files = self._required_files_from_contract(ctx.output_contract)
        return {
            "schema_version": self.schema_version,
            "selected_skill": self.code,
            "output_contract": ctx.output_contract or {"required_files": []},
            "packaging_rules": {
                "include": [
                    "outputs/**",
                    "job/execution-plan.json",
                    "job/request.md",
                    "logs/opencode-last-message.md",
                    "manifest.json",
                ]
            },
            "timeouts": {
                "soft_seconds": 15 * 60,
                "hard_seconds": 20 * 60,
            },
            "retry_policy": {"max_attempts": 2, "backoff_seconds": [30, 120]},
            "hints": {
                "required_files": required_files,
                "write_readme_for_assumptions": True,
            },
        }

    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """构建发送给 OpenCode 的最终提示词。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        - plan: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return (
            "你是企业级任务执行代理，请严格遵守以下约束:\n"
            f"- 工作目录: {ctx.workspace_dir}\n"
            "- 输入目录: inputs/\n"
            "- 输出目录: outputs/\n"
            "- 计划文件: job/execution-plan.json\n"
            "- 需求文件: job/request.md\n"
            f"- 必须先加载并执行 skill: {ctx.selected_skill}\n"
            "- 严禁修改 inputs/ 原始文件\n"
            "- 所有结果仅写入 outputs/\n"
            "- 若信息不足，请做最小合理假设，并写入 outputs/README.md\n"
            "- 优先满足 execution-plan.json 中 output_contract 的产物约束\n\n"
            "execution-plan.json:\n"
            f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n"
        )

    def validate_outputs(self, ctx: JobContext) -> None:
        """校验技能执行后的输出是否满足契约。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        outputs_dir = ctx.workspace_dir / "outputs"
        if not outputs_dir.exists() or not any(outputs_dir.rglob("*")):
            raise ValueError("outputs/ is empty")
        required_files = self._required_files_from_contract(ctx.output_contract)
        for required in required_files:
            if not (outputs_dir / required).exists():
                raise ValueError(f"missing required output file: {required}")

    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """返回技能附加产物清单定义。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return [{"kind": "default", "path": "outputs/"}]

