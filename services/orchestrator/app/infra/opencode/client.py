from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class OpenCodeCredentials:
    username: str
    password: str | None


class OpenCodeClient:
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
        if self._credentials.password:
            return self._credentials.username, self._credentials.password
        return None

    def _client_or_raise(self) -> httpx.Client:
        if self._closed:
            raise RuntimeError("OpenCodeClient is already closed")
        return self._client

    def _params(self, directory: Path | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if directory is not None:
            params["directory"] = str(directory)
        if extra:
            params.update(extra)
        return params

    def close(self) -> None:
        if self._closed:
            return
        self._client.close()
        self._closed = True

    def health(self) -> dict[str, Any]:
        response = self._client_or_raise().get("/global/health")
        response.raise_for_status()
        return response.json()

    def create_session(self, directory: Path, title: str = "headless-run") -> str:
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
        request_body: dict[str, Any] = {
            "agent": agent,
            "parts": [{"type": "text", "text": prompt}],
        }
        if model:
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
        response = self._client_or_raise().get("/permission", params=self._params(directory))
        response.raise_for_status()
        return list(response.json())

    def reply_permission(self, directory: Path, request_id: str, reply: str, message: str | None = None) -> None:
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
        response = self._client_or_raise().get("/session/status", params=self._params(directory))
        response.raise_for_status()
        return response.json()

    def get_last_message(self, directory: Path, session_id: str, limit: int = 1) -> list[dict[str, Any]]:
        response = self._client_or_raise().get(
            f"/session/{session_id}/message",
            params=self._params(directory, {"limit": limit}),
        )
        response.raise_for_status()
        return list(response.json())

    def abort_session(self, directory: Path, session_id: str) -> None:
        response = self._client_or_raise().post(
            f"/session/{session_id}/abort",
            params=self._params(directory),
        )
        response.raise_for_status()

    def read_file(self, directory: Path, path: str) -> list[dict[str, Any]]:
        response = self._client_or_raise().get(
            "/file",
            params=self._params(directory, {"path": path}),
        )
        response.raise_for_status()
        return list(response.json())

    def read_file_content(self, directory: Path, path: str) -> dict[str, Any]:
        response = self._client_or_raise().get(
            "/file/content",
            params=self._params(directory, {"path": path}),
        )
        response.raise_for_status()
        return response.json()
