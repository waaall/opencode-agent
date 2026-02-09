"""权限策略测试：验证路径越界、工作区写入与危险命令拦截。"""

from pathlib import Path

from app.infra.security.permission_policy import PermissionPolicyEngine


def test_permission_policy_rejects_outside_workspace() -> None:
    """越界路径应被拒绝。"""
    policy = PermissionPolicyEngine()
    decision = policy.decide(
        {"permission": "file.write", "patterns": ["/etc/passwd"], "metadata": {}},
        workspace_dir=Path("/data/opencode-jobs/job-1"),
    )
    assert decision.reply == "reject"


def test_permission_policy_allows_workspace_edit() -> None:
    """工作区内文件编辑应放行。"""
    policy = PermissionPolicyEngine()
    decision = policy.decide(
        {
            "permission": "file.edit",
            "patterns": ["outputs/report.md"],
            "metadata": {},
        },
        workspace_dir=Path("/data/opencode-jobs/job-1"),
    )
    assert decision.reply == "once"


def test_permission_policy_rejects_dangerous_command() -> None:
    """危险命令应被拒绝。"""
    policy = PermissionPolicyEngine()
    decision = policy.decide(
        {
            "permission": "shell.execute",
            "patterns": ["outputs/report.md"],
            "metadata": {"command": "sudo rm -rf /"},
        },
        workspace_dir=Path("/data/opencode-jobs/job-1"),
    )
    assert decision.reply == "reject"
