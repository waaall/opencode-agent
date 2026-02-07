from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.infra.storage.workspace import sha256_file


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ArtifactEntry:
    relative_path: str
    absolute_path: Path
    size_bytes: int
    sha256: str


class ArtifactManager:
    def collect_output_entries(self, workspace_dir: Path) -> list[ArtifactEntry]:
        outputs_root = workspace_dir / "outputs"
        entries: list[ArtifactEntry] = []
        if not outputs_root.exists():
            return entries
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
        bundle_dir = workspace_dir / "bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_dir / "result.zip"

        extra_files: list[ArtifactEntry] = []
        for relative in ("job/execution-plan.json", "job/request.md", "logs/opencode-last-message.md"):
            path = workspace_dir / relative
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
            for entry in self.collect_output_entries(workspace_dir):
                zipf.write(entry.absolute_path, arcname=entry.relative_path)
            for entry in extra_files:
                zipf.write(entry.absolute_path, arcname=entry.relative_path)
            zipf.writestr("manifest.json", manifest_bytes)
        return bundle_path, manifest

