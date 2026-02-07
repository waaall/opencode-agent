from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.domain.enums import FileCategory, JobStatus
from app.domain.models import JobContext
from app.domain.skills.registry import SkillRegistry
from app.infra.db.repository import JobRepository
from app.infra.opencode.client import OpenCodeClient
from app.infra.opencode.event_bridge import OpenCodeEventBridge
from app.infra.security.permission_policy import PermissionPolicyEngine
from app.infra.storage.artifact import ArtifactManager
from app.infra.storage.workspace import WorkspaceManager, sha256_file


class JobAbortedError(RuntimeError):
    pass


class JobExecutor:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: JobRepository,
        skill_registry: SkillRegistry,
        workspace_manager: WorkspaceManager,
        artifact_manager: ArtifactManager,
        opencode_client: OpenCodeClient,
        event_bridge: OpenCodeEventBridge,
        permission_policy: PermissionPolicyEngine,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._skill_registry = skill_registry
        self._workspace_manager = workspace_manager
        self._artifact_manager = artifact_manager
        self._opencode_client = opencode_client
        self._event_bridge = event_bridge
        self._permission_policy = permission_policy

    def run(self, job_id: str) -> None:
        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if job.status == JobStatus.aborted.value:
            return

        workspace_dir = Path(job.workspace_dir)
        input_files = self._repository.list_job_files(job_id, FileCategory.input)
        input_paths = [workspace_dir / item.relative_path for item in input_files]

        ctx = JobContext(
            job_id=job.id,
            tenant_id=job.tenant_id,
            requirement=job.requirement_text,
            workspace_dir=workspace_dir,
            input_files=input_paths,
            selected_skill=job.selected_skill,
            agent=job.agent,
            model=job.model_json,
            output_contract=job.output_contract_json,
        )
        skill = self._skill_registry.get(job.selected_skill)

        try:
            self._set_status_or_abort(job_id, JobStatus.running)
            session_id = self._opencode_client.create_session(workspace_dir, title=f"job-{job_id}")
            self._repository.set_session_id(job_id, session_id)
            self._ensure_not_aborted(job_id, workspace_dir, session_id)

            plan_path = workspace_dir / "job" / "execution-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            prompt = skill.build_prompt(ctx, plan)
            self._opencode_client.prompt_async(
                directory=workspace_dir,
                session_id=session_id,
                prompt=prompt,
                agent=ctx.agent,
                model=ctx.model,
            )
            self._repository.add_event(
                job_id,
                source="worker",
                event_type="opencode.prompt_async.sent",
                message="prompt_async submitted",
            )

            self._wait_for_completion(job_id, workspace_dir, session_id)
            self._ensure_not_aborted(job_id, workspace_dir, session_id)

            try:
                messages = self._opencode_client.get_last_message(workspace_dir, session_id, limit=1)
                if messages:
                    self._workspace_manager.write_last_message(
                        workspace_dir,
                        json.dumps(messages[0], ensure_ascii=False, indent=2),
                    )
            except Exception as exc:
                self._repository.add_event(
                    job_id,
                    source="worker",
                    event_type="opencode.last_message.read.failed",
                    message=str(exc),
                )

            self._set_status_or_abort(job_id, JobStatus.verifying)
            self._verify_inputs_unchanged(job_id, workspace_dir)
            skill.validate_outputs(ctx)

            self._set_status_or_abort(job_id, JobStatus.packaging)
            bundle_path, _manifest = self._artifact_manager.build_bundle(
                workspace_dir=workspace_dir,
                job_id=job_id,
                session_id=session_id,
            )
            self._repository.set_result_bundle(job_id, str(bundle_path))

            outputs = self._artifact_manager.collect_output_entries(workspace_dir)
            for entry in outputs:
                self._repository.upsert_job_file(
                    job_id,
                    category=FileCategory.output,
                    relative_path=entry.relative_path,
                    mime_type=None,
                    size_bytes=entry.size_bytes,
                    sha256=entry.sha256,
                )

            self._repository.upsert_job_file(
                job_id,
                category=FileCategory.bundle,
                relative_path=str(bundle_path.relative_to(workspace_dir)),
                mime_type="application/zip",
                size_bytes=bundle_path.stat().st_size,
                sha256=sha256_file(bundle_path),
            )
            log_path = workspace_dir / "logs" / "opencode-last-message.md"
            if log_path.exists():
                self._repository.upsert_job_file(
                    job_id,
                    category=FileCategory.log,
                    relative_path=str(log_path.relative_to(workspace_dir)),
                    mime_type="text/markdown",
                    size_bytes=log_path.stat().st_size,
                    sha256=sha256_file(log_path),
                )

            self._set_status_or_abort(job_id, JobStatus.succeeded)
        except JobAbortedError:
            self._repository.set_status(job_id, JobStatus.aborted)
            self._repository.add_event(
                job_id,
                source="worker",
                event_type="job.aborted",
                status=JobStatus.aborted.value,
                message="job aborted",
            )
        except Exception as exc:
            self._repository.set_status(
                job_id,
                JobStatus.failed,
                error_code="job_execution_failed",
                error_message=str(exc),
            )
            self._repository.add_event(
                job_id,
                source="worker",
                event_type="job.failed",
                status=JobStatus.failed.value,
                message=str(exc),
            )
            raise

    def _wait_for_completion(self, job_id: str, workspace_dir: Path, session_id: str) -> None:
        deadline = time.monotonic() + self._settings.job_soft_timeout_seconds
        approval_wait_started_at: float | None = None
        last_status_poll = 0.0

        while time.monotonic() < deadline:
            self._ensure_not_aborted(job_id, workspace_dir, session_id)
            now = time.monotonic()
            if now - last_status_poll >= 2:
                done, approval_wait_started_at = self._sync_completion_state(
                    job_id=job_id,
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                    approval_wait_started_at=approval_wait_started_at,
                )
                last_status_poll = now
                if done:
                    return

            try:
                for event in self._event_bridge.iter_session_events(workspace_dir, session_id):
                    self._ensure_not_aborted(job_id, workspace_dir, session_id)
                    self._record_stream_event(job_id, event)
                    if str(event.get("event", "")).startswith("permission."):
                        self._process_permissions(job_id, workspace_dir)

                    now = time.monotonic()
                    if now - last_status_poll >= 2:
                        done, approval_wait_started_at = self._sync_completion_state(
                            job_id=job_id,
                            workspace_dir=workspace_dir,
                            session_id=session_id,
                            approval_wait_started_at=approval_wait_started_at,
                        )
                        last_status_poll = now
                        if done:
                            return
                    if now >= deadline:
                        break
            except httpx.ReadTimeout:
                # No stream event in this window; compensate with session polling below.
                pass
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                self._repository.add_event(
                    job_id,
                    source="worker",
                    event_type="opencode.event.stream.disconnected",
                    message=str(exc),
                )

            done, approval_wait_started_at = self._sync_completion_state(
                job_id=job_id,
                workspace_dir=workspace_dir,
                session_id=session_id,
                approval_wait_started_at=approval_wait_started_at,
            )
            last_status_poll = time.monotonic()
            if done:
                return

            time.sleep(1)

        try:
            self._opencode_client.abort_session(workspace_dir, session_id)
        except Exception:
            pass
        raise TimeoutError("job execution timeout")

    def _sync_completion_state(
        self,
        *,
        job_id: str,
        workspace_dir: Path,
        session_id: str,
        approval_wait_started_at: float | None,
    ) -> tuple[bool, float | None]:
        self._process_permissions(job_id, workspace_dir)
        status_map = self._opencode_client.get_session_status(workspace_dir)
        session_status = status_map.get(session_id) if isinstance(status_map, dict) else None
        state_type = session_status.get("type") if isinstance(session_status, dict) else None

        if state_type == "idle":
            self._repository.add_event(
                job_id,
                source="opencode",
                event_type="session.updated",
                message="session idle",
                payload=self._as_event_payload(session_status),
            )
            return True, None
        if state_type == "retry":
            self._repository.add_event(
                job_id,
                source="opencode",
                event_type="session.retry",
                message=str(session_status.get("message")) if isinstance(session_status, dict) else None,
                payload=self._as_event_payload(session_status),
            )

        pending_permissions = self._opencode_client.list_permissions(workspace_dir)
        current_waiting = any(item.get("sessionID") == session_id for item in pending_permissions)
        if current_waiting:
            if approval_wait_started_at is None:
                approval_wait_started_at = time.monotonic()
                self._set_status_or_abort(job_id, JobStatus.waiting_approval)
            elif time.monotonic() - approval_wait_started_at > self._settings.permission_wait_timeout_seconds:
                raise TimeoutError("permission waiting timeout")
        else:
            approval_wait_started_at = None
            job = self._repository.get_job(job_id)
            if job and job.status == JobStatus.waiting_approval.value:
                self._set_status_or_abort(job_id, JobStatus.running)
        return False, approval_wait_started_at

    def _record_stream_event(self, job_id: str, event: dict[str, Any]) -> None:
        event_type = str(event.get("event") or "message")
        if not (event_type.startswith("session.") or event_type.startswith("permission.")):
            return

        data = event.get("data")
        message: str | None = None
        if isinstance(data, dict):
            message = data.get("message")
            if message is None and "type" in data:
                message = str(data.get("type"))
            elif message is not None:
                message = str(message)
        elif isinstance(data, str):
            message = data

        self._repository.add_event(
            job_id,
            source="opencode",
            event_type=event_type,
            message=message,
            payload=self._as_event_payload(data),
        )

    @staticmethod
    def _as_event_payload(data: Any) -> dict[str, Any] | None:
        if data is None:
            return None
        if isinstance(data, dict):
            return data
        return {"data": data}

    def _process_permissions(self, job_id: str, workspace_dir: Path) -> None:
        permissions = self._opencode_client.list_permissions(workspace_dir)
        for request in permissions:
            request_id = str(request.get("id", ""))
            if not request_id:
                continue
            decision = self._permission_policy.decide(request, workspace_dir)
            self._opencode_client.reply_permission(
                workspace_dir,
                request_id=request_id,
                reply=decision.reply,
                message=decision.message,
            )
            self._repository.add_permission_action(job_id, request_id, decision.reply, "policy-engine")
            self._repository.add_event(
                job_id,
                source="worker",
                event_type="permission.replied",
                message=f"{request_id}:{decision.reply}",
                payload={"request_id": request_id, "reply": decision.reply},
            )

    def _verify_inputs_unchanged(self, job_id: str, workspace_dir: Path) -> None:
        input_files = self._repository.list_job_files(job_id, FileCategory.input)
        for file_meta in input_files:
            path = workspace_dir / file_meta.relative_path
            if not path.exists():
                raise ValueError(f"input file missing: {file_meta.relative_path}")
            current_sha = sha256_file(path)
            if current_sha != file_meta.sha256:
                raise ValueError(f"input file modified unexpectedly: {file_meta.relative_path}")

    def _set_status_or_abort(self, job_id: str, status: JobStatus) -> None:
        changed = self._repository.set_status(job_id, status)
        if not changed:
            raise JobAbortedError("job was aborted")

    def _ensure_not_aborted(self, job_id: str, workspace_dir: Path, session_id: str | None = None) -> None:
        job = self._repository.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if job.status != JobStatus.aborted.value:
            return
        if session_id:
            try:
                self._opencode_client.abort_session(workspace_dir, session_id)
            except Exception:
                pass
        raise JobAbortedError("job was aborted")
