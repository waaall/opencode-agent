"""产物管理器：收集输出文件、生成清单并构建可下载压缩包。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.infra.storage.workspace import sha256_file


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ArtifactEntry:
    """产物条目元数据，描述文件路径、大小与哈希。"""
    relative_path: str
    absolute_path: Path
    size_bytes: int
    sha256: str


class ArtifactManager:
    """产物管理器，负责汇总输出、构建清单与打包。"""
    def collect_output_entries(self, workspace_dir: Path) -> list[ArtifactEntry]:
        """收集 outputs 目录下所有产物文件元信息。
        参数:
        - workspace_dir: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        outputs_root = workspace_dir / "outputs"
        entries: list[ArtifactEntry] = []
        if not outputs_root.exists():
            return entries
        # 统一排序确保 manifest 与压缩包内容顺序稳定，便于追踪差异。
        for file_path in sorted(path for path in outputs_root.rglob("*") if path.is_file()):
            entries.append(
                ArtifactEntry(
                    relative_path=str(file_path.relative_to(workspace_dir)),
                    absolute_path=file_path,
                    size_bytes=file_path.stat().st_size,
                    sha256=sha256_file(file_path),
                )
            )
        return entries

    def build_manifest(
        self,
        *,
        job_id: str,
        session_id: str | None,
        workspace_dir: Path,
        extra_entries: list[ArtifactEntry] | None = None,
    ) -> dict[str, object]:
        """生成产物清单字典，包含文件摘要与元数据。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - extra_entries: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        entries = self.collect_output_entries(workspace_dir)
        if extra_entries:
            entries.extend(extra_entries)
        return {
            "job_id": job_id,
            "session_id": session_id,
            "generated_at": utcnow_iso(),
            "files": [
                {
                    "path": entry.relative_path,
                    "size_bytes": entry.size_bytes,
                    "sha256": entry.sha256,
                }
                for entry in entries
            ],
        }

    def build_bundle(
        self,
        *,
        workspace_dir: Path,
        job_id: str,
        session_id: str | None,
    ) -> tuple[Path, dict[str, object]]:
        """构建结果压缩包并写入 manifest.json。
        参数:
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - job_id: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        bundle_dir = workspace_dir / "bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_dir / "result.zip"

        extra_files: list[ArtifactEntry] = []
        for relative in ("job/execution-plan.json", "job/request.md", "logs/opencode-last-message.md"):
            path = workspace_dir / relative
            # 将关键上下文文件一起纳入包，支持离线复盘执行过程。
            if path.exists() and path.is_file():
                extra_files.append(
                    ArtifactEntry(
                        relative_path=relative,
                        absolute_path=path,
                        size_bytes=path.stat().st_size,
                        sha256=sha256_file(path),
                    )
                )

        manifest = self.build_manifest(
            job_id=job_id,
            session_id=session_id,
            workspace_dir=workspace_dir,
            extra_entries=extra_files,
        )
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_entry = ArtifactEntry(
            relative_path="manifest.json",
            absolute_path=workspace_dir / "bundle" / "manifest.json",
            size_bytes=len(manifest_bytes),
            sha256=manifest_sha,
        )
        manifest_entry.absolute_path.write_bytes(manifest_bytes)

        with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as zipf:
            # 输出产物 + 附加上下文 + 清单三类文件共同构成最终交付包。
            for entry in self.collect_output_entries(workspace_dir):
                zipf.write(entry.absolute_path, arcname=entry.relative_path)
            for entry in extra_files:
                zipf.write(entry.absolute_path, arcname=entry.relative_path)
            zipf.writestr("manifest.json", manifest_bytes)
        return bundle_path, manifest
