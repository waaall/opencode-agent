"""日志初始化：统一 JSON 结构、异步队列写入与 DEBUG 路由开关。"""

from __future__ import annotations

import json
import logging
import logging.config
import re
import sys
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import SimpleQueue
from typing import Any

from app.config import Settings
from app.infra.logging.context import get_log_context

_listener: QueueListener | None = None

_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)(x-api-key\s*[:=]\s*)[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)(password\s*[:=]\s*)[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)(token\s*[:=]\s*)[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)(secret\s*[:=]\s*)[^\s,;]+"), r"\1***"),
)


def redact_text(value: str | None, mode: str) -> str | None:
    """按模式脱敏文本，避免凭据和敏感字段落盘。"""
    if value is None:
        return None
    text = str(value)
    if mode.lower() == "off":
        return text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    if mode.lower() == "strict":
        text = re.sub(r"(?i)(authorization|password|token|secret)([^,\s}]*)", r"\1=***", text)
    return text


def render_payload_preview(payload: Any, *, max_chars: int, redaction_mode: str) -> str | None:
    """将 payload 转为截断后的预览文本，避免写入大对象。"""
    if payload is None:
        return None
    if isinstance(payload, str):
        serialized = payload
    else:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except TypeError:
            serialized = str(payload)
    redacted = redact_text(serialized, redaction_mode) or ""
    if len(redacted) <= max_chars:
        return redacted
    return f"{redacted[:max_chars]}...(truncated)"


class DebugRoutingFilter(logging.Filter):
    """控制默认日志级别，并允许指定模块/job_id 放行 DEBUG。"""

    def __init__(self, *, min_level: int, debug_modules: set[str], debug_job_ids: set[str]) -> None:
        super().__init__()
        self._min_level = min_level
        self._debug_modules = debug_modules
        self._debug_job_ids = debug_job_ids

    def _module_debug_enabled(self, logger_name: str) -> bool:
        return any(logger_name == item or logger_name.startswith(f"{item}.") for item in self._debug_modules)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= self._min_level:
            return True
        if record.levelno != logging.DEBUG:
            return False
        if self._module_debug_enabled(record.name):
            return True
        job_id = getattr(record, "job_id", None) or get_log_context().get("job_id")
        if job_id and job_id in self._debug_job_ids:
            return True
        return False


class ContextInjectionFilter(logging.Filter):
    """在日志入队前将 contextvars 写入 record，避免跨线程丢失。"""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_log_context()
        for key in ("request_id", "job_id", "session_id", "task_id"):
            if getattr(record, key, None) is None and ctx.get(key) is not None:
                setattr(record, key, ctx[key])
        return True


class StructuredJsonFormatter(logging.Formatter):
    """将 LogRecord 规整为统一 JSON 行格式。"""

    def __init__(
        self,
        *,
        service: str,
        process_role: str,
        redaction_mode: str,
        payload_preview_chars: int,
    ) -> None:
        super().__init__()
        self._service = service
        self._process_role = process_role
        self._redaction_mode = redaction_mode
        self._payload_preview_chars = payload_preview_chars

    @staticmethod
    def _coerce_number(value: Any) -> int | float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            text = str(value)
            return int(text) if text.isdigit() else float(text)
        except Exception:
            return None

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_log_context()
        request_id = getattr(record, "request_id", None) or ctx.get("request_id")
        job_id = getattr(record, "job_id", None) or ctx.get("job_id")
        session_id = getattr(record, "session_id", None) or ctx.get("session_id")
        task_id = getattr(record, "task_id", None) or ctx.get("task_id")

        error_text = getattr(record, "error", None)
        if error_text is None and record.exc_info:
            error_text = self.formatException(record.exc_info)

        payload_preview = render_payload_preview(
            getattr(record, "payload_preview", None),
            max_chars=self._payload_preview_chars,
            redaction_mode=self._redaction_mode,
        )
        message = redact_text(record.getMessage(), self._redaction_mode)
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self._service,
            "process_role": self._process_role,
            "module": record.name,
            "event": getattr(record, "event", None),
            "request_id": request_id,
            "job_id": job_id,
            "session_id": session_id,
            "task_id": task_id,
            "external_service": getattr(record, "external_service", None),
            "op": getattr(record, "op", None),
            "duration_ms": self._coerce_number(getattr(record, "duration_ms", None)),
            "status_code": self._coerce_number(getattr(record, "status_code", None)),
            "retry": self._coerce_number(getattr(record, "retry", None)),
            "message": message,
            "error_type": getattr(record, "error_type", None),
            "error": redact_text(str(error_text), self._redaction_mode) if error_text is not None else None,
            "payload_preview": payload_preview,
        }
        return json.dumps(entry, ensure_ascii=False)


def _parse_level(level_text: str) -> int:
    return getattr(logging, str(level_text).upper(), logging.INFO)


def configure_logging(settings: Settings, *, process_role: str) -> Path:
    """初始化全局日志输出，默认写 JSONL 文件并将 ERROR 同步到 stderr。"""
    global _listener
    shutdown_logging()

    log_root = settings.log_dir
    if not log_root.is_absolute():
        log_root = (Path.cwd() / log_root).resolve()
    role_dir = log_root / process_role
    role_dir.mkdir(parents=True, exist_ok=True)
    log_file = role_dir / "orchestrator.jsonl"

    queue_obj: SimpleQueue[logging.LogRecord] = SimpleQueue()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "queue": {
                    "class": "logging.handlers.QueueHandler",
                    "queue": queue_obj,
                }
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["queue"],
            },
        }
    )

    root_logger = logging.getLogger()
    queue_handler = next((item for item in root_logger.handlers if isinstance(item, QueueHandler)), None)
    if queue_handler is None:
        raise RuntimeError("queue logging handler is not configured")
    queue_handler.addFilter(ContextInjectionFilter())
    queue_handler.addFilter(
        DebugRoutingFilter(
            min_level=_parse_level(settings.log_level),
            debug_modules=set(settings.log_debug_modules_list()),
            debug_job_ids=set(settings.log_debug_job_ids_list()),
        )
    )

    formatter = StructuredJsonFormatter(
        service="opencode-orchestrator",
        process_role=process_role,
        redaction_mode=settings.log_redaction_mode,
        payload_preview_chars=settings.log_payload_preview_chars,
    )
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    _listener = QueueListener(queue_obj, file_handler, stderr_handler, respect_handler_level=True)
    _listener.start()

    # 第三方库默认降噪，避免业务日志被淹没。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("s3transfer").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    return log_file


def shutdown_logging() -> None:
    """停止队列监听器并关闭底层句柄。"""
    global _listener
    if _listener is None:
        return
    try:
        _listener.stop()
        for handler in _listener.handlers:
            try:
                handler.close()
            except Exception:
                pass
    finally:
        _listener = None
