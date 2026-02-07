from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class StoredFile:
    relative_path: str
    absolute_path: Path
    size_bytes: int
    sha256: str
    mime_type: str | None


class WorkspaceManager:
    def __init__(self, data_root: Path, max_upload_file_size_bytes: int) -> None:
        self._data_root = data_root
        self._max_upload_file_size_bytes = max_upload_file_size_bytes

    def workspace_dir(self, job_id: str) -> Path:
        return self._data_root / job_id

    def create_workspace(self, job_id: str) -> Path:
        root = self.workspace_dir(job_id)
        for segment in ("job", "inputs", "outputs", "logs", "bundle"):
            (root / segment).mkdir(parents=True, exist_ok=True)
        return root

    def sanitize_filename(self, filename: str) -> str:
        clean_name = Path(filename).name.strip()
        clean_name = FILENAME_SAFE_RE.sub("_", clean_name)
        return clean_name or "upload.bin"

    def store_input_file(self, workspace_dir: Path, filename: str, content: bytes, mime_type: str | None) -> StoredFile:
        if len(content) == 0:
            raise ValueError(f"empty upload is not allowed: {filename}")
        if len(content) > self._max_upload_file_size_bytes:
            raise ValueError(f"file exceeds size limit: {filename}")
        safe_name = self.sanitize_filename(filename)
        target = workspace_dir / "inputs" / safe_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            idx = 1
            while True:
                candidate = workspace_dir / "inputs" / f"{stem}_{idx}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                idx += 1
        target.write_bytes(content)
        return StoredFile(
            relative_path=str(Path("inputs") / target.name),
            absolute_path=target,
            size_bytes=len(content),
            sha256=sha256_bytes(content),
            mime_type=mime_type,
        )

    def write_request_markdown(self, workspace_dir: Path, requirement: str) -> Path:
        path = workspace_dir / "job" / "request.md"
        path.write_text(requirement.strip() + "\n", encoding="utf-8")
        return path

    def write_execution_plan(self, workspace_dir: Path, plan: dict[str, object]) -> Path:
        path = workspace_dir / "job" / "execution-plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_last_message(self, workspace_dir: Path, content: str) -> Path:
        path = workspace_dir / "logs" / "opencode-last-message.md"
        path.write_text(content, encoding="utf-8")
        return path
