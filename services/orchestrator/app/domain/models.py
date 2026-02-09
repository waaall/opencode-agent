"""领域数据结构定义：任务上下文与技能描述等核心值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JobContext:
    """技能执行上下文，聚合作业执行所需的关键信息。"""
    job_id: str
    tenant_id: str
    requirement: str
    workspace_dir: Path
    input_files: list[Path]
    selected_skill: str
    agent: str
    model: dict[str, str] | None
    output_contract: dict[str, Any] | None


@dataclass(slots=True)
class SkillDescriptor:
    """技能元信息描述对象，用于接口返回与路由展示。"""
    code: str
    name: str
    aliases: tuple[str, ...]
    version: str
    schema_version: str
    description: str
    task_type: str
