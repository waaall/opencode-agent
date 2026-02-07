from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JobContext:
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
    code: str
    name: str
    aliases: tuple[str, ...]
    version: str
    schema_version: str
    description: str
    task_type: str
