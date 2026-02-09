"""权限策略引擎：根据请求内容与路径范围给出自动审批决策。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PermissionDecision:
    """权限审批决策结果，包含回复动作与可选说明。"""
    reply: str  # once | always | reject
    message: str | None = None


class PermissionPolicyEngine:
    """权限策略引擎，根据风险规则自动做出审批决策。"""

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
        """根据权限类型、路径范围和命令风险给出审批动作。"""
        permission = str(request.get("permission", "")).lower()
        patterns = request.get("patterns", []) or []
        metadata = request.get("metadata", {}) or {}

        command = str(metadata.get("command", "")).lower()
        # 先做命令级黑名单拦截，避免高危命令进入后续流程。
        if any(token in command for token in self._dangerous_tokens):
            return PermissionDecision(reply="reject", message="rejected by security policy: dangerous command")

        for pattern in patterns:
            # 对疑似路径的 pattern 做工作区边界校验，阻断越权访问。
            if self._looks_like_path(pattern) and not self._path_in_workspace(pattern, workspace_dir):
                return PermissionDecision(reply="reject", message="rejected by security policy: outside workspace")

        # 文件类权限默认一次性放行；Shell 权限默认拒绝，走显式白名单策略。
        if "edit" in permission or "write" in permission or "file" in permission:
            return PermissionDecision(reply="once")
        if "shell" in permission:
            return PermissionDecision(reply="reject", message="rejected by security policy: shell not whitelisted")
        return PermissionDecision(reply="once")

    @staticmethod
    def _looks_like_path(value: object) -> bool:
        """判断模式字符串是否可能为路径。"""
        text = str(value)
        return "/" in text or text.startswith(".")

    @staticmethod
    def _path_in_workspace(value: object, workspace_dir: Path) -> bool:
        """判断目标路径是否位于工作区根目录内。"""
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
