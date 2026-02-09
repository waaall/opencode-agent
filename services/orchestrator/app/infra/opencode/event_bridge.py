"""OpenCode 事件桥接器：消费 SSE 事件流并按会话过滤。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.infra.opencode.client import OpenCodeCredentials


class OpenCodeEventBridge:
    """OpenCode 事件桥接器，负责解析 SSE 事件流。"""

    def __init__(
        self,
        base_url: str,
        credentials: OpenCodeCredentials,
        timeout_seconds: int = 300,
        stream_read_timeout_seconds: int = 10,
    ) -> None:
        """__init__ 函数实现业务步骤并返回处理结果。
        参数:
        - base_url: 业务参数，具体语义见调用上下文。
        - credentials: 业务参数，具体语义见调用上下文。
        - timeout_seconds: 业务参数，具体语义见调用上下文。
        - stream_read_timeout_seconds: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._base_url = base_url.rstrip("/")
        self._credentials = credentials
        self._closed = False
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                timeout=timeout_seconds,
                connect=min(10.0, timeout_seconds),
                read=float(stream_read_timeout_seconds),
            ),
            auth=self._auth(),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        )

    def _auth(self) -> tuple[str, str] | None:
        """根据凭据构造 HTTP 基础认证参数。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if self._credentials.password:
            return self._credentials.username, self._credentials.password
        return None

    def _client_or_raise(self) -> httpx.Client:
        """返回可用客户端；若已关闭则抛出异常。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if self._closed:
            raise RuntimeError("OpenCodeEventBridge is already closed")
        return self._client

    def close(self) -> None:
        """关闭底层 HTTP 客户端连接池。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if self._closed:
            return
        self._client.close()
        self._closed = True

    def iter_events(self, directory: Path) -> Iterator[dict[str, Any]]:
        """持续读取 SSE 流并组装为事件字典。
        参数:
        - directory: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        with self._client_or_raise().stream("GET", "/event", params={"directory": str(directory)}) as response:
            response.raise_for_status()
            event_name: str | None = None
            data_lines: list[str] = []
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    if data_lines:
                        # SSE 以空行分隔事件，累积 data 行后统一组装 payload。
                        payload_text = "\n".join(data_lines)
                        data = self._parse_json(payload_text)
                        yield {"event": event_name or "message", "data": data}
                    event_name = None
                    data_lines = []
                    continue
                if line.startswith(":"):
                    # 以冒号开头的是 SSE 注释帧，属于 keep-alive，可直接跳过。
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())

    def iter_session_events(self, directory: Path, session_id: str) -> Iterator[dict[str, Any]]:
        """仅输出包含目标会话 ID 的事件。
        参数:
        - directory: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        for event in self.iter_events(directory):
            data = event.get("data")
            if self._contains_session_id(data, session_id):
                yield event

    def _contains_session_id(self, payload: Any, session_id: str) -> bool:
        """递归检查事件负载中是否包含指定会话 ID。
        参数:
        - payload: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if isinstance(payload, dict):
            for key in ("sessionID", "session_id"):
                value = payload.get(key)
                if value == session_id:
                    return True
            return any(self._contains_session_id(value, session_id) for value in payload.values())
        if isinstance(payload, list):
            return any(self._contains_session_id(item, session_id) for item in payload)
        return False

    @staticmethod
    def _parse_json(value: str) -> Any:
        """尽量将字符串解析为 JSON，失败时返回原始字符串。
        参数:
        - value: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
