"""日志上下文：基于 contextvars 透传 request/job/session/task 标识。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator

_UNSET = object()

_request_id_var: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_job_id_var: ContextVar[str | None] = ContextVar("log_job_id", default=None)
_session_id_var: ContextVar[str | None] = ContextVar("log_session_id", default=None)
_task_id_var: ContextVar[str | None] = ContextVar("log_task_id", default=None)


def get_log_context() -> dict[str, str | None]:
    """返回当前协程/线程下的日志上下文字段。"""
    return {
        "request_id": _request_id_var.get(),
        "job_id": _job_id_var.get(),
        "session_id": _session_id_var.get(),
        "task_id": _task_id_var.get(),
    }


@contextmanager
def bind_log_context(
    *,
    request_id: str | None | object = _UNSET,
    job_id: str | None | object = _UNSET,
    session_id: str | None | object = _UNSET,
    task_id: str | None | object = _UNSET,
) -> Iterator[None]:
    """在上下文范围内绑定日志字段，并在退出时自动恢复。"""
    tokens: list[tuple[ContextVar[Any], Token[Any]]] = []
    if request_id is not _UNSET:
        tokens.append((_request_id_var, _request_id_var.set(request_id)))
    if job_id is not _UNSET:
        tokens.append((_job_id_var, _job_id_var.set(job_id)))
    if session_id is not _UNSET:
        tokens.append((_session_id_var, _session_id_var.set(session_id)))
    if task_id is not _UNSET:
        tokens.append((_task_id_var, _task_id_var.set(task_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)

