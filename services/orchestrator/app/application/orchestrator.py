from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.domain.enums import FileCategory, JobStatus
from app.domain.models import JobContext
from app.domain.skills.registry import SkillRegistry
from app.domain.skills.router import SkillRouter
from app.infra.db.models import JobORM
from app.infra.db.repository import InputFileRecord, JobRepository
from app.infra.opencode.client import OpenCodeClient
from app.infra.storage.artifact import ArtifactManager
from app.infra.storage.workspace import WorkspaceManager


@dataclass(slots=True)
class UploadedFileData:
    filename: str
    content: bytes
    content_type: str | None


class OrchestratorService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: JobRepository,
        skill_registry: SkillRegistry,
        skill_router: SkillRouter,
        workspace_manager: WorkspaceManager,
        artifact_manager: ArtifactManager,
        opencode_client: OpenCodeClient,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._skill_registry = skill_registry
        self._skill_router = skill_router
        self._workspace_manager = workspace_manager
        self._artifact_manager = artifact_manager
        self._opencode_client = opencode_client

    def create_job(
        self,
        *,
        requirement: str,
        files: list[UploadedFileData],
        skill_code: str | None,
        agent: str | None,
        model: dict[str, str] | None,
        output_contract: dict[str, Any] | None,
        idempotency_key: str | None,
        tenant_id: str | None = None,
        created_by: str | None = None,
    ) -> JobORM:
        if not requirement.strip():
            raise ValueError("requirement is required")
        if not files:
            raise ValueError("at least one file is required")

        tenant = tenant_id or self._settings.default_tenant_id
        actor = created_by or self._settings.default_created_by
        req_hash = self._build_requirement_hash(requirement, files)

        if idempotency_key:
            existing = self._repository.get_job_by_idempotency(tenant, idempotency_key, req_hash)
            if existing:
                return existing

        job_id = str(uuid4())
        workspace_dir = self._workspace_manager.create_workspace(job_id)

        stored_inputs = [
            self._workspace_manager.store_input_file(workspace_dir, file.filename, file.content, file.content_type)
            for file in files
        ]

        selected_skill, route_reason = self._skill_router.select(
            requirement=requirement,
            files=[item.absolute_path for item in stored_inputs],
            skill_code=skill_code,
        )
        chosen_agent = agent or self._settings.default_agent

        ctx = JobContext(
            job_id=job_id,
            tenant_id=tenant,
            requirement=requirement,
            workspace_dir=workspace_dir,
            input_files=[item.absolute_path for item in stored_inputs],
            selected_skill=selected_skill.code,
            agent=chosen_agent,
            model=model,
            output_contract=output_contract,
        )
        execution_plan = selected_skill.build_execution_plan(ctx)
        self._workspace_manager.write_request_markdown(workspace_dir, requirement)
        self._workspace_manager.write_execution_plan(workspace_dir, execution_plan)

        input_records = [
            InputFileRecord(
                relative_path=item.relative_path,
                mime_type=item.mime_type,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
            )
            for item in stored_inputs
        ]
        job = self._repository.create_job(
            job_id=job_id,
            tenant_id=tenant,
            workspace_dir=str(workspace_dir),
            requirement_text=requirement,
            selected_skill=selected_skill.code,
            agent=chosen_agent,
            model_json=model,
            output_contract_json=execution_plan.get("output_contract") if isinstance(execution_plan, dict) else None,
            created_by=actor,
            input_files=input_records,
            idempotency_key=idempotency_key,
            requirement_hash=req_hash,
        )
        if route_reason:
            self._repository.add_event(
                job.id,
                source="api",
                event_type="skill.router.fallback",
                message=route_reason,
                payload={"selected_skill": selected_skill.code},
            )
        return job

    def start_job(self, job_id: str) -> JobORM:
        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if job.status not in {JobStatus.created.value, JobStatus.failed.value}:
            raise ValueError(f"job cannot be started from status={job.status}")

        self._opencode_client.health()
        self._repository.set_status(job_id, JobStatus.queued)

        from app.worker.tasks import run_job_task

        task = run_job_task.delay(job_id)
        self._repository.add_event(
            job_id,
            source="api",
            event_type="job.enqueued",
            status=JobStatus.queued.value,
            message=task.id,
            payload={"task_id": task.id},
        )
        started = self._repository.get_job(job_id)
        if started is None:
            raise RuntimeError("job disappeared after enqueue")
        return started

    def abort_job(self, job_id: str) -> JobORM:
        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if job.session_id:
            self._opencode_client.abort_session(Path(job.workspace_dir), job.session_id)
        self._repository.set_status(job_id, JobStatus.aborted)
        aborted = self._repository.get_job(job_id)
        if aborted is None:
            raise RuntimeError("job not found after abort")
        return aborted

    def get_job(self, job_id: str) -> JobORM:
        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return job

    def list_job_events(self, job_id: str, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        events = self._repository.list_events(job_id, after_id=after_id, limit=limit)
        return [
            {
                "id": event.id,
                "job_id": event.job_id,
                "status": event.status,
                "source": event.source,
                "event_type": event.event_type,
                "message": event.message,
                "payload": event.payload,
                "created_at": event.created_at,
            }
            for event in events
        ]

    def list_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        files = self._repository.list_job_files(job_id)
        allowed_categories = {FileCategory.output.value, FileCategory.bundle.value}
        return [
            {
                "id": item.id,
                "category": item.category,
                "relative_path": item.relative_path,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "created_at": item.created_at,
            }
            for item in files
            if item.category in allowed_categories
        ]

    def get_bundle_path(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if not job.result_bundle_path:
            raise FileNotFoundError("bundle not generated yet")
        path = Path(job.result_bundle_path)
        if not path.exists():
            raise FileNotFoundError("bundle path missing on disk")
        return path

    def get_artifact_path(self, job_id: str, artifact_id: int) -> Path:
        artifact = self._repository.get_job_file(artifact_id)
        if artifact is None or artifact.job_id != job_id:
            raise FileNotFoundError("artifact not found")
        if artifact.category not in {FileCategory.output.value, FileCategory.bundle.value}:
            raise FileNotFoundError("artifact category is not downloadable")
        job = self.get_job(job_id)
        path = Path(job.workspace_dir) / artifact.relative_path
        if not path.exists():
            raise FileNotFoundError("artifact file missing")
        return path

    def list_skills(self, task_type: str | None = None) -> list[dict[str, Any]]:
        descriptors = self._skill_registry.list_descriptors()
        if not task_type:
            return descriptors
        return [skill for skill in descriptors if skill.get("task_type") == task_type]

    def get_skill(self, skill_code: str) -> dict[str, Any]:
        skill = self._skill_registry.get(skill_code)
        descriptor = skill.descriptor().__dict__
        descriptor["sample_output_contract"] = skill.build_execution_plan(
            JobContext(
                job_id="sample",
                tenant_id=self._settings.default_tenant_id,
                requirement="sample",
                workspace_dir=Path("/tmp/sample"),
                input_files=[],
                selected_skill=skill.code,
                agent=self._settings.default_agent,
                model=None,
                output_contract=None,
            )
        ).get("output_contract")
        return descriptor

    @staticmethod
    def _build_requirement_hash(requirement: str, files: list[UploadedFileData]) -> str:
        digest = hashlib.sha256()
        digest.update(requirement.strip().encode("utf-8"))
        for file in sorted(files, key=lambda item: item.filename):
            content_hash = hashlib.sha256(file.content).hexdigest()
            digest.update(file.filename.encode("utf-8"))
            digest.update(content_hash.encode("utf-8"))
        return digest.hexdigest()
