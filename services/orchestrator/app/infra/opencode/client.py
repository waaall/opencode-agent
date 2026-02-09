"""OpenCode HTTP 客户端：封装会话、权限、消息与文件读取接口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class OpenCodeCredentials:
    """OpenCode 服务认证凭据对象。"""
    username: str
    password: str | None


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

    def health(self) -> dict[str, Any]:
        """调用 OpenCode 健康检查接口。"""
        response = self._client_or_raise().get("/global/health")
        response.raise_for_status()
        return response.json()

    def create_session(self, directory: Path, title: str = "headless-run") -> str:
        """创建新会话并返回 session_id。"""
        response = self._client_or_raise().post(
            "/session",
            params=self._params(directory),
            json={"title": title},
        )
        response.raise_for_status()
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
        response = self._client_or_raise().post(
            f"/session/{session_id}/prompt_async",
            params=self._params(directory),
            json=request_body,
        )
        response.raise_for_status()

    def list_permissions(self, directory: Path) -> list[dict[str, Any]]:
        """查询当前目录下待审批权限请求。"""
        response = self._client_or_raise().get("/permission", params=self._params(directory))
        response.raise_for_status()
        return list(response.json())

    def reply_permission(self, directory: Path, request_id: str, reply: str, message: str | None = None) -> None:
        """回复指定权限请求。"""
        body: dict[str, Any] = {"reply": reply}
        if message:
            body["message"] = message
        response = self._client_or_raise().post(
            f"/permission/{request_id}/reply",
            params=self._params(directory),
            json=body,
        )
        response.raise_for_status()

    def get_session_status(self, directory: Path) -> dict[str, Any]:
        """查询会话状态快照。"""
        response = self._client_or_raise().get("/session/status", params=self._params(directory))
        response.raise_for_status()
        return response.json()

    def get_last_message(self, directory: Path, session_id: str, limit: int = 1) -> list[dict[str, Any]]:
        """读取会话最后消息列表。"""
        response = self._client_or_raise().get(
            f"/session/{session_id}/message",
            params=self._params(directory, {"limit": limit}),
        )
        response.raise_for_status()
        return list(response.json())

    def abort_session(self, directory: Path, session_id: str) -> None:
        """主动中止 OpenCode 会话执行。"""
        response = self._client_or_raise().post(
            f"/session/{session_id}/abort",
            params=self._params(directory),
        )
        response.raise_for_status()

    def read_file(self, directory: Path, path: str) -> list[dict[str, Any]]:
        """读取工作目录中的文件元信息。"""
        response = self._client_or_raise().get(
            "/file",
            params=self._params(directory, {"path": path}),
        )
        response.raise_for_status()
        return list(response.json())

    def read_file_content(self, directory: Path, path: str) -> dict[str, Any]:
        """读取工作目录中的文件内容。"""
        response = self._client_or_raise().get(
            "/file/content",
            params=self._params(directory, {"path": path}),
        )
        response.raise_for_status()
        return response.json()
