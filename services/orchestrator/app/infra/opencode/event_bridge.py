from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.infra.opencode.client import OpenCodeCredentials


class OpenCodeEventBridge:
    """Stream OpenCode /event and filter by session_id."""

    def __init__(
        self,
        base_url: str,
        credentials: OpenCodeCredentials,
        timeout_seconds: int = 300,
        stream_read_timeout_seconds: int = 10,
    ) -> None:
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
        if self._credentials.password:
            return self._credentials.username, self._credentials.password
        return None

    def _client_or_raise(self) -> httpx.Client:
        if self._closed:
            raise RuntimeError("OpenCodeEventBridge is already closed")
        return self._client

    def close(self) -> None:
        if self._closed:
            return
        self._client.close()
        self._closed = True

    def iter_events(self, directory: Path) -> Iterator[dict[str, Any]]:
        with self._client_or_raise().stream("GET", "/event", params={"directory": str(directory)}) as response:
            response.raise_for_status()
            event_name: str | None = None
            data_lines: list[str] = []
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    if data_lines:
                        payload_text = "\n".join(data_lines)
                        data = self._parse_json(payload_text)
                        yield {"event": event_name or "message", "data": data}
                    event_name = None
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())

    def iter_session_events(self, directory: Path, session_id: str) -> Iterator[dict[str, Any]]:
        for event in self.iter_events(directory):
            data = event.get("data")
            if self._contains_session_id(data, session_id):
                yield event

    def _contains_session_id(self, payload: Any, session_id: str) -> bool:
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
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
