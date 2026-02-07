from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.domain.models import JobContext, SkillDescriptor


class BaseSkill(ABC):
    code: str
    name: str
    aliases: tuple[str, ...] = ()
    version: str = "0.1.0"
    schema_version: str = "1.0.0"
    description: str = ""
    task_type: str = "general"

    @abstractmethod
    def score(self, requirement: str, files: list[Path]) -> float:
        """Return routing score in range [0, 1]."""

    @abstractmethod
    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """Build execution-plan.json payload."""

    @abstractmethod
    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """Build final prompt sent to OpenCode."""

    @abstractmethod
    def validate_outputs(self, ctx: JobContext) -> None:
        """Validate outputs under workspace outputs/; raise ValueError if invalid."""

    @abstractmethod
    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """Return extra skill-specific manifest items."""

    def descriptor(self) -> SkillDescriptor:
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
        if not output_contract:
            return []
        for key in ("required_files", "files", "required"):
            value = output_contract.get(key)
            if isinstance(value, list):
                return [str(item) for item in value if item]
        return []

