from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.enums import FileCategory, JobStatus
from app.infra.db.models import (
    IdempotencyRecordORM,
    JobEventORM,
    JobFileORM,
    JobORM,
    PermissionActionORM,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class InputFileRecord:
    relative_path: str
    mime_type: str | None
    size_bytes: int
    sha256: str


class JobRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_job(self, job_id: str) -> JobORM | None:
        with self._session_factory() as db:
            return db.get(JobORM, job_id)

    def get_job_by_idempotency(self, tenant_id: str, idempotency_key: str, requirement_hash: str) -> JobORM | None:
        with self._session_factory() as db:
            stmt: Select[tuple[IdempotencyRecordORM]] = select(IdempotencyRecordORM).where(
                IdempotencyRecordORM.tenant_id == tenant_id,
                IdempotencyRecordORM.idempotency_key == idempotency_key,
                IdempotencyRecordORM.requirement_hash == requirement_hash,
            )
            row = db.execute(stmt).scalars().first()
            if row is None:
                return None
            return db.get(JobORM, row.job_id)

    def create_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        workspace_dir: str,
        requirement_text: str,
        selected_skill: str,
        agent: str,
        model_json: dict[str, str] | None,
        output_contract_json: dict[str, Any] | None,
        created_by: str,
        input_files: list[InputFileRecord],
        idempotency_key: str | None,
        requirement_hash: str,
    ) -> JobORM:
        with self._session_factory.begin() as db:
            if idempotency_key:
                existing = db.execute(
                    select(IdempotencyRecordORM).where(
                        IdempotencyRecordORM.tenant_id == tenant_id,
                        IdempotencyRecordORM.idempotency_key == idempotency_key,
                        IdempotencyRecordORM.requirement_hash == requirement_hash,
                    )
                ).scalars().first()
                if existing:
                    existing_job = db.get(JobORM, existing.job_id)
                    if existing_job is not None:
                        return existing_job

            job = JobORM(
                id=job_id,
                tenant_id=tenant_id,
                status=JobStatus.created.value,
                workspace_dir=workspace_dir,
                requirement_text=requirement_text,
                selected_skill=selected_skill,
                agent=agent,
                model_json=model_json,
                output_contract_json=output_contract_json,
                created_by=created_by,
            )
            db.add(job)
            db.flush()

            for file_meta in input_files:
                db.add(
                    JobFileORM(
                        job_id=job.id,
                        category=FileCategory.input.value,
                        relative_path=file_meta.relative_path,
                        mime_type=file_meta.mime_type,
                        size_bytes=file_meta.size_bytes,
                        sha256=file_meta.sha256,
                    )
                )

            if idempotency_key:
                db.add(
                    IdempotencyRecordORM(
                        tenant_id=tenant_id,
                        idempotency_key=idempotency_key,
                        requirement_hash=requirement_hash,
                        job_id=job.id,
                    )
                )

            db.add(
                JobEventORM(
                    job_id=job.id,
                    status=JobStatus.created.value,
                    source="api",
                    event_type="job.created",
                    message="job created",
                    payload={"selected_skill": selected_skill},
                )
            )
            db.flush()
            return job

    def add_event(
        self,
        job_id: str,
        *,
        source: str,
        event_type: str,
        status: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JobEventORM:
        with self._session_factory.begin() as db:
            event = JobEventORM(
                job_id=job_id,
                status=status,
                source=source,
                event_type=event_type,
                message=message,
                payload=payload,
            )
            db.add(event)
            db.flush()
            db.refresh(event)
            return event

    def list_events(self, job_id: str, after_id: int = 0, limit: int = 200) -> list[JobEventORM]:
        with self._session_factory() as db:
            stmt = (
                select(JobEventORM)
                .where(JobEventORM.job_id == job_id, JobEventORM.id > after_id)
                .order_by(JobEventORM.id.asc())
                .limit(limit)
            )
            return list(db.execute(stmt).scalars().all())

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        emit_event: bool = True,
    ) -> bool:
        with self._session_factory.begin() as db:
            job = db.get(JobORM, job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            if job.status == JobStatus.aborted.value and status != JobStatus.aborted:
                return False
            job.status = status.value
            job.error_code = error_code
            job.error_message = error_message
            job.updated_at = utcnow()
            db.add(job)
            if emit_event:
                db.add(
                    JobEventORM(
                        job_id=job_id,
                        status=status.value,
                        source="worker",
                        event_type="job.status.changed",
                        message=status.value,
                    )
                )
            return True

    def set_session_id(self, job_id: str, session_id: str) -> None:
        with self._session_factory.begin() as db:
            job = db.get(JobORM, job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            job.session_id = session_id
            job.updated_at = utcnow()
            db.add(job)
            db.add(
                JobEventORM(
                    job_id=job_id,
                    source="worker",
                    event_type="opencode.session.created",
                    message=session_id,
                    payload={"session_id": session_id},
                )
            )

    def add_permission_action(self, job_id: str, request_id: str, action: str, actor: str) -> None:
        with self._session_factory.begin() as db:
            db.add(
                PermissionActionORM(
                    job_id=job_id,
                    request_id=request_id,
                    action=action,
                    actor=actor,
                )
            )

    def set_result_bundle(self, job_id: str, bundle_path: str) -> None:
        with self._session_factory.begin() as db:
            job = db.get(JobORM, job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            job.result_bundle_path = bundle_path
            job.updated_at = utcnow()
            db.add(job)

    def upsert_job_file(
        self,
        job_id: str,
        *,
        category: FileCategory,
        relative_path: str,
        mime_type: str | None,
        size_bytes: int,
        sha256: str,
    ) -> None:
        with self._session_factory.begin() as db:
            existing = db.execute(
                select(JobFileORM).where(
                    JobFileORM.job_id == job_id,
                    JobFileORM.category == category.value,
                    JobFileORM.relative_path == relative_path,
                )
            ).scalars().first()
            if existing:
                existing.mime_type = mime_type
                existing.size_bytes = size_bytes
                existing.sha256 = sha256
                db.add(existing)
                return
            db.add(
                JobFileORM(
                    job_id=job_id,
                    category=category.value,
                    relative_path=relative_path,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                )
            )

    def list_job_files(self, job_id: str, category: FileCategory | None = None) -> list[JobFileORM]:
        with self._session_factory() as db:
            stmt = select(JobFileORM).where(JobFileORM.job_id == job_id)
            if category:
                stmt = stmt.where(JobFileORM.category == category.value)
            stmt = stmt.order_by(JobFileORM.created_at.asc())
            return list(db.execute(stmt).scalars().all())

    def get_job_file(self, file_id: int) -> JobFileORM | None:
        with self._session_factory() as db:
            return db.get(JobFileORM, file_id)
