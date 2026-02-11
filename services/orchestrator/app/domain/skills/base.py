"""技能抽象基类，约束评分、执行计划、提示词与输出校验接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.domain.models import JobContext, SkillDescriptor


class BaseSkill(ABC):
    """技能抽象基类，定义各技能必须实现的统一接口。"""
    code: str
    name: str
    aliases: tuple[str, ...] = ()
    version: str = "0.1.0"
    schema_version: str = "1.0.0"
    description: str = ""
    task_type: str = "general"

    @abstractmethod
    def score(self, requirement: str, files: list[Path]) -> float:
        """根据需求文本和输入文件计算技能匹配分数。"""

    @abstractmethod
    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """构建技能执行计划。"""

    @abstractmethod
    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """基于作业上下文和执行计划构建 prompt。"""

    @abstractmethod
    def validate_outputs(self, ctx: JobContext) -> None:
        """校验技能输出是否满足约束。"""

    @abstractmethod
    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """定义技能产物清单。"""

    def prepare_workspace(self, ctx: JobContext, plan: dict[str, Any]) -> None:
        """按需在工作区生成技能运行时文件；默认无需额外准备。"""
        return None

    def descriptor(self) -> SkillDescriptor:
        """返回技能描述对象。"""
        return SkillDescriptor(
            code=self.code,
            name=self.name,
            aliases=self.aliases,
            version=self.version,
            schema_version=self.schema_version,
            description=self.description,
            task_type=self.task_type,
        )

    def _required_files_from_contract(self, output_contract: dict[str, Any] | None) -> list[str]:
        """从输出契约中提取必需文件列表。"""
        if not output_contract:
            return []
        for key in ("required_files", "files", "required"):
            value = output_contract.get(key)
            if isinstance(value, list):
                return [str(item) for item in value if item]
        return []
