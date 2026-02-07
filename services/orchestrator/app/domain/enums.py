from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
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
    input = "input"
    output = "output"
    bundle = "bundle"
    log = "log"


class EventSource(str, Enum):
    api = "api"
    worker = "worker"
    opencode = "opencode"

