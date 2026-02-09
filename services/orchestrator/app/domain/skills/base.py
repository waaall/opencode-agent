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
        """根据需求与输入文件计算技能匹配分数。
        参数:
        - requirement: 业务参数，具体语义见调用上下文。
        - files: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """

    @abstractmethod
    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """构建当前技能的执行计划数据结构。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """

    @abstractmethod
    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """构建发送给 OpenCode 的最终提示词。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        - plan: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """

    @abstractmethod
    def validate_outputs(self, ctx: JobContext) -> None:
        """校验技能执行后的输出是否满足契约。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """

    @abstractmethod
    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """返回技能附加产物清单定义。
        参数:
        - ctx: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """

    def descriptor(self) -> SkillDescriptor:
        """返回技能描述对象，供外部展示与路由使用。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """从输出契约中提取必需文件列表。
        参数:
        - output_contract: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if not output_contract:
            return []
        for key in ("required_files", "files", "required"):
            value = output_contract.get(key)
            if isinstance(value, list):
                return [str(item) for item in value if item]
        return []

