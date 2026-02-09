"""工作区管理器：创建目录、保存上传文件并写入任务元数据。"""

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
    """流式计算文件 SHA-256 摘要。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        # 分块读取大文件，避免一次性加载导致内存峰值过高。
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class StoredFile:
    """已落盘输入文件描述，保存相对路径与摘要信息。"""
    relative_path: str
    absolute_path: Path
    size_bytes: int
    sha256: str
    mime_type: str | None


class WorkspaceManager:
    """工作区文件管理器，负责目录与任务文件组织。"""
    def __init__(self, data_root: Path, max_upload_file_size_bytes: int) -> None:
        self._data_root = data_root
        self._max_upload_file_size_bytes = max_upload_file_size_bytes

    def workspace_dir(self, job_id: str) -> Path:
        return self._data_root / job_id

    def create_workspace(self, job_id: str) -> Path:
        """创建作业执行所需的标准目录结构。"""
        root = self.workspace_dir(job_id)
        # 统一目录结构，避免执行阶段出现路径分支判断。
        for segment in ("job", "inputs", "outputs", "logs", "bundle"):
            (root / segment).mkdir(parents=True, exist_ok=True)
        return root

    def sanitize_filename(self, filename: str) -> str:
        """清洗上传文件名，移除潜在非法字符。"""
        clean_name = Path(filename).name.strip()
        # 仅保留白名单字符，防止路径穿越或奇异文件名导致写入风险。
        clean_name = FILENAME_SAFE_RE.sub("_", clean_name)
        return clean_name or "upload.bin"

    def store_input_file(self, workspace_dir: Path, filename: str, content: bytes, mime_type: str | None) -> StoredFile:
        """将上传文件落盘到 inputs 目录并返回元数据。"""
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
                # 同名文件自动追加序号，确保多文件上传不会互相覆盖。
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
        """写入任务需求文档 request.md。"""
        path = workspace_dir / "job" / "request.md"
        path.write_text(requirement.strip() + "\n", encoding="utf-8")
        return path

    def write_execution_plan(self, workspace_dir: Path, plan: dict[str, object]) -> Path:
        """写入执行计划 execution-plan.json。"""
        path = workspace_dir / "job" / "execution-plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_last_message(self, workspace_dir: Path, content: str) -> Path:
        """写入会话最后消息日志。"""
        path = workspace_dir / "logs" / "opencode-last-message.md"
        path.write_text(content, encoding="utf-8")
        return path
