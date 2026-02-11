"""演示文稿技能实现：面向 PPT 生成场景提供专用计划与验收规则。"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.models import JobContext
from app.domain.skills.base import BaseSkill


class PptSkill(BaseSkill):
    """演示文稿技能实现，产出幻灯片及相关预览文件。"""
    code = "ppt"
    name = "PPT Generator"
    aliases = ("slides", "presentation")
    version = "1.0.0"
    schema_version = "1.0.0"
    description = "Generate slide deck from requirement and media assets."
    task_type = "presentation"

    PPT_KEYWORDS = (
        "ppt",
        "幻灯片",
        "演示",
        "presentation",
        "slides",
        "deck",
    )
    STRONG_MEDIA_EXTENSIONS = {".pptx"}
    WEAK_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}

    def score(self, requirement: str, files: list[Path]) -> float:
        """基于关键词和素材类型为 PPT 任务打分。"""
        text = requirement.lower()
        keyword_hits = sum(1 for keyword in self.PPT_KEYWORDS if keyword in text)
        file_score = 0.0
        for path in files:
            suffix = path.suffix.lower()
            if suffix in self.STRONG_MEDIA_EXTENSIONS:
                file_score += 0.45
            elif suffix in self.WEAK_MEDIA_EXTENSIONS:
                file_score += 0.12
        score = 0.08 + keyword_hits * 0.14 + file_score
        return min(1.0, score)

    def build_execution_plan(self, ctx: JobContext) -> dict[str, object]:
        """构建 PPT 技能执行计划。"""
        default_contract: dict[str, object] = {"required_files": ["slides.pptx"]}
        merged_contract = default_contract if ctx.output_contract is None else ctx.output_contract
        return {
            "schema_version": self.schema_version,
            "selected_skill": self.code,
            "output_contract": merged_contract,
            "packaging_rules": {"include": ["outputs/**", "job/request.md", "job/execution-plan.json"]},
            "timeouts": {"soft_seconds": 15 * 60, "hard_seconds": 20 * 60},
            "retry_policy": {"max_attempts": 2, "backoff_seconds": [30, 120]},
            "ppt_rules": {
                "theme": "professional",
                "language": "zh-CN",
                "write_assumptions_to_readme": True,
            },
        }

    def build_prompt(self, ctx: JobContext, plan: dict[str, object]) -> str:
        """生成 PPT 任务执行 prompt。"""
        return (
            "请执行 ppt skill 完成演示文稿任务。\n"
            "硬性要求:\n"
            "- 基于 inputs/ 读取文本与图片素材\n"
            "- 结果输出为 outputs/slides.pptx\n"
            "- 可选输出支持 outputs/preview/*.png 作为预览图\n"
            "- 若信息不足，做最小合理假设并写入 outputs/README.md\n"
            "- 严禁修改 inputs/\n"
            "- 严格满足 execution-plan.json 的 output_contract\n\n"
            "execution-plan.json:\n"
            f"{json.dumps(plan, ensure_ascii=False, indent=2)}\n"
        )

    def validate_outputs(self, ctx: JobContext) -> None:
        """校验 PPT 输出是否满足契约。"""
        outputs_dir = ctx.workspace_dir / "outputs"
        slides = outputs_dir / "slides.pptx"
        if not slides.exists():
            raise ValueError("ppt skill requires outputs/slides.pptx")
        required_files = self._required_files_from_contract(ctx.output_contract)
        for required in required_files:
            if not (outputs_dir / required).exists():
                raise ValueError(f"missing required output file: {required}")

    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, str]]:
        """返回 PPT 技能产物清单。"""
        return [{"kind": "slides", "path": "outputs/slides.pptx"}]
