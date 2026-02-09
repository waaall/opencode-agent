"""领域枚举定义：统一任务状态、文件分类和事件来源取值。"""

from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """作业生命周期状态枚举。"""
    created = "created"
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    verifying = "verifying"
    packaging = "packaging"
    succeeded = "succeeded"
    failed = "failed"
    aborted = "aborted"


class FileCategory(str, Enum):
    """作业文件分类枚举。"""
    input = "input"
    output = "output"
    bundle = "bundle"
    log = "log"


class EventSource(str, Enum):
    """事件来源枚举。"""
    api = "api"
    worker = "worker"
    opencode = "opencode"

