"""仓储实现：封装作业生命周期、事件流与产物元数据持久化操作。"""

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
    """输入文件持久化记录，作为创建作业时的写库参数。"""
    relative_path: str
    mime_type: str | None
    size_bytes: int
    sha256: str


class JobRepository:
    """作业仓储实现，封装数据库读写与状态流转。"""
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_job(self, job_id: str) -> JobORM | None:
        """按主键查询作业。"""
        with self._session_factory() as db:
            return db.get(JobORM, job_id)

    def get_job_by_idempotency(self, tenant_id: str, idempotency_key: str, requirement_hash: str) -> JobORM | None:
        """按租户、幂等键和需求哈希查询已有作业。"""
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
        """在一个事务内创建作业、输入文件与首条事件。"""
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
                        # 并发场景下幂等记录已存在时直接复用已有作业。
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
        """写入单条作业事件。"""
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
        """按游标分页查询事件流。"""
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
        """更新作业状态，并按需写入状态变更事件。"""
        with self._session_factory.begin() as db:
            job = db.get(JobORM, job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            # 一旦进入 aborted，除再次写 aborted 外禁止被其他状态覆盖。
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
        """为作业绑定会话 ID，并记录会话创建事件。"""
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
        """记录一次权限审批动作。"""
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
        """写入结果压缩包路径。"""
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
        """按 `job_id + category + relative_path` 幂等写入文件元数据。"""
        with self._session_factory.begin() as db:
            existing = db.execute(
                select(JobFileORM).where(
                    JobFileORM.job_id == job_id,
                    JobFileORM.category == category.value,
                    JobFileORM.relative_path == relative_path,
                )
            ).scalars().first()
            if existing:
                # 相同路径文件更新为最新元数据，避免重复记录。
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
        """查询作业文件列表，可按类别过滤。"""
        with self._session_factory() as db:
            stmt = select(JobFileORM).where(JobFileORM.job_id == job_id)
            if category:
                stmt = stmt.where(JobFileORM.category == category.value)
            stmt = stmt.order_by(JobFileORM.created_at.asc())
            return list(db.execute(stmt).scalars().all())

    def get_job_file(self, file_id: int) -> JobFileORM | None:
        """按主键查询单个作业文件。"""
        with self._session_factory() as db:
            return db.get(JobFileORM, file_id)
