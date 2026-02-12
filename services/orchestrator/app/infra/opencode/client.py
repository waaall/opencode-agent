"""OpenCode HTTP 客户端：封装会话、权限、消息与文件读取接口。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class OpenCodeCredentials:
    """OpenCode 服务认证凭据对象。"""
    username: str
    password: str | None


logger = logging.getLogger(__name__)


class OpenCodeClient:
    """OpenCode 同步 HTTP 客户端封装。"""
    def __init__(self, base_url: str, credentials: OpenCodeCredentials, timeout_seconds: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._credentials = credentials
        self._closed = False
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            auth=self._auth(),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    def _auth(self) -> tuple[str, str] | None:
        """根据凭据构造 HTTP 基础认证参数。"""
        # 仅在配置了密码时启用基础认证，兼容无鉴权的本地开发环境。
        if self._credentials.password:
            return self._credentials.username, self._credentials.password
        return None

    def _client_or_raise(self) -> httpx.Client:
        """返回可用客户端；若已关闭则抛出异常。"""
        if self._closed:
            raise RuntimeError("OpenCodeClient is already closed")
        return self._client

    def _params(self, directory: Path | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """合并 directory 与额外查询参数。"""
        params: dict[str, Any] = {}
        if directory is not None:
            # OpenCode API 依赖 directory 路由到具体工作区上下文。
            params["directory"] = str(directory)
        if extra:
            params.update(extra)
        return params

    def close(self) -> None:
        """关闭底层 HTTP 客户端连接池。"""
        if self._closed:
            return
        self._client.close()
        self._closed = True

    def _request(
        self,
        *,
        method: str,
        path: str,
        op: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        payload_preview: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """发送 HTTP 请求并记录结构化日志。"""
        started = time.perf_counter()
        try:
            response = self._client_or_raise().request(method, path, params=params, json=json_body)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = None
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                status_code = exc.response.status_code
            logger.error(
                "opencode request failed",
                extra={
                    "event": "opencode.request.failed",
                    "external_service": "opencode",
                    "op": op,
                    "duration_ms": duration_ms,
                    "status_code": status_code,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "payload_preview": payload_preview,
                },
            )
            raise
        return response

    def health(self) -> dict[str, Any]:
        """调用 OpenCode 健康检查接口。"""
        response = self._request(method="GET", path="/global/health", op="global.health")
        return response.json()

    def create_session(self, directory: Path, title: str = "headless-run") -> str:
        """创建新会话并返回 session_id。"""
        response = self._request(
            method="POST",
            path="/session",
            op="session.create",
            params=self._params(directory),
            json_body={"title": title},
            payload_preview={"directory": str(directory), "title": title},
        )
        payload = response.json()
        session_id = payload.get("id") or payload.get("sessionID")
        if not session_id:
            raise RuntimeError("missing session id from OpenCode response")
        return str(session_id)

    def prompt_async(
        self,
        *,
        directory: Path,
        session_id: str,
        prompt: str,
        agent: str,
        model: dict[str, str] | None,
    ) -> None:
        """向指定会话异步发送 prompt。"""
        request_body: dict[str, Any] = {
            "agent": agent,
            "parts": [{"type": "text", "text": prompt}],
        }
        if model:
            # 模型配置为可选字段，仅在调用方明确指定时透传。
            request_body["model"] = {
                "providerID": model["providerID"],
                "modelID": model["modelID"],
            }
        self._request(
            method="POST",
            path=f"/session/{session_id}/prompt_async",
            op="session.prompt_async",
            params=self._params(directory),
            json_body=request_body,
            payload_preview={
                "directory": str(directory),
                "session_id": session_id,
                "agent": agent,
                "has_model": bool(model),
                "prompt_chars": len(prompt),
            },
        )

    def list_permissions(self, directory: Path) -> list[dict[str, Any]]:
        """查询当前目录下待审批权限请求。"""
        response = self._request(
            method="GET",
            path="/permission",
            op="permission.list",
            params=self._params(directory),
            payload_preview={"directory": str(directory)},
        )
        return list(response.json())

    def reply_permission(self, directory: Path, request_id: str, reply: str, message: str | None = None) -> None:
        """回复指定权限请求。"""
        body: dict[str, Any] = {"reply": reply}
        if message:
            body["message"] = message
        self._request(
            method="POST",
            path=f"/permission/{request_id}/reply",
            op="permission.reply",
            params=self._params(directory),
            json_body=body,
            payload_preview={"directory": str(directory), "request_id": request_id, "reply": reply},
        )

    def get_session_status(self, directory: Path) -> dict[str, Any]:
        """查询会话状态快照。"""
        response = self._request(
            method="GET",
            path="/session/status",
            op="session.status",
            params=self._params(directory),
            payload_preview={"directory": str(directory)},
        )
        return response.json()

    def get_last_message(self, directory: Path, session_id: str, limit: int = 1) -> list[dict[str, Any]]:
        """读取会话最后消息列表。"""
        response = self._request(
            method="GET",
            path=f"/session/{session_id}/message",
            op="session.last_message",
            params=self._params(directory, {"limit": limit}),
            payload_preview={"directory": str(directory), "session_id": session_id, "limit": limit},
        )
        return list(response.json())

    def abort_session(self, directory: Path, session_id: str) -> None:
        """主动中止 OpenCode 会话执行。"""
        self._request(
            method="POST",
            path=f"/session/{session_id}/abort",
            op="session.abort",
            params=self._params(directory),
            payload_preview={"directory": str(directory), "session_id": session_id},
        )

    def read_file(self, directory: Path, path: str) -> list[dict[str, Any]]:
        """读取工作目录中的文件元信息。"""
        response = self._request(
            method="GET",
            path="/file",
            op="file.read",
            params=self._params(directory, {"path": path}),
            payload_preview={"directory": str(directory), "path": path},
        )
        return list(response.json())

    def read_file_content(self, directory: Path, path: str) -> dict[str, Any]:
        """读取工作目录中的文件内容。"""
        response = self._request(
            method="GET",
            path="/file/content",
            op="file.read_content",
            params=self._params(directory, {"path": path}),
            payload_preview={"directory": str(directory), "path": path},
        )
        return response.json()
