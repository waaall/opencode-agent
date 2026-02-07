from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PermissionDecision:
    reply: str  # once | always | reject
    message: str | None = None


class PermissionPolicyEngine:
    """Enterprise-safe permission decision policy.

    Baseline behavior:
    - Allow workspace-local file edit actions.
    - Reject outside workspace paths and high-risk shell patterns.
    """

    def __init__(self) -> None:
        self._dangerous_tokens = (
            "sudo ",
            "rm -rf /",
            "mkfs",
            "shutdown",
            "reboot",
            "curl ",
            "wget ",
            "scp ",
            "ssh ",
        )

    def decide(self, request: dict[str, Any], workspace_dir: Path) -> PermissionDecision:
        permission = str(request.get("permission", "")).lower()
        patterns = request.get("patterns", []) or []
        metadata = request.get("metadata", {}) or {}

        command = str(metadata.get("command", "")).lower()
        if any(token in command for token in self._dangerous_tokens):
            return PermissionDecision(reply="reject", message="rejected by security policy: dangerous command")

        for pattern in patterns:
            if self._looks_like_path(pattern) and not self._path_in_workspace(pattern, workspace_dir):
                return PermissionDecision(reply="reject", message="rejected by security policy: outside workspace")

        if "edit" in permission or "write" in permission or "file" in permission:
            return PermissionDecision(reply="once")
        if "shell" in permission:
            return PermissionDecision(reply="reject", message="rejected by security policy: shell not whitelisted")
        return PermissionDecision(reply="once")

    @staticmethod
    def _looks_like_path(value: object) -> bool:
        text = str(value)
        return "/" in text or text.startswith(".")

    @staticmethod
    def _path_in_workspace(value: object, workspace_dir: Path) -> bool:
        try:
            candidate = Path(str(value))
            if not candidate.is_absolute():
                candidate = (workspace_dir / candidate).resolve()
            else:
                candidate = candidate.resolve()
            root = workspace_dir.resolve()
            return candidate == root or root in candidate.parents
        except OSError:
            return False

