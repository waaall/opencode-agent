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
    """返回当前 UTC 时间。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
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
        """__init__ 函数实现业务步骤并返回处理结果。
        参数:
        - session_factory: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._session_factory = session_factory

    def get_job(self, job_id: str) -> JobORM | None:
        """查询作业详情并返回下载链接等视图字段。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        with self._session_factory() as db:
            return db.get(JobORM, job_id)

    def get_job_by_idempotency(self, tenant_id: str, idempotency_key: str, requirement_hash: str) -> JobORM | None:
        """根据租户、幂等键与需求哈希查询历史作业。
        参数:
        - tenant_id: 业务参数，具体语义见调用上下文。
        - idempotency_key: 业务参数，具体语义见调用上下文。
        - requirement_hash: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """创建作业与输入文件记录，并完成技能路由与执行计划写入。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - tenant_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - requirement_text: 业务参数，具体语义见调用上下文。
        - selected_skill: 业务参数，具体语义见调用上下文。
        - agent: 业务参数，具体语义见调用上下文。
        - model_json: 业务参数，具体语义见调用上下文。
        - output_contract_json: 业务参数，具体语义见调用上下文。
        - created_by: 业务参数，具体语义见调用上下文。
        - input_files: 业务参数，具体语义见调用上下文。
        - idempotency_key: 业务参数，具体语义见调用上下文。
        - requirement_hash: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """写入一条作业事件记录。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - source: 业务参数，具体语义见调用上下文。
        - event_type: 业务参数，具体语义见调用上下文。
        - status: 业务参数，具体语义见调用上下文。
        - message: 业务参数，具体语义见调用上下文。
        - payload: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """返回资源列表。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - after_id: 业务参数，具体语义见调用上下文。
        - limit: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """更新作业状态并按需追加状态变更事件。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - status: 业务参数，具体语义见调用上下文。
        - error_code: 业务参数，具体语义见调用上下文。
        - error_message: 业务参数，具体语义见调用上下文。
        - emit_event: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """绑定 OpenCode 会话 ID 到作业记录。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """记录一次权限审批动作。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - request_id: 业务参数，具体语义见调用上下文。
        - action: 业务参数，具体语义见调用上下文。
        - actor: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """写入结果压缩包路径。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - bundle_path: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """按类别与相对路径更新或插入文件元数据。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - category: 业务参数，具体语义见调用上下文。
        - relative_path: 业务参数，具体语义见调用上下文。
        - mime_type: 业务参数，具体语义见调用上下文。
        - size_bytes: 业务参数，具体语义见调用上下文。
        - sha256: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """查询作业文件列表，可按类别过滤。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - category: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        with self._session_factory() as db:
            stmt = select(JobFileORM).where(JobFileORM.job_id == job_id)
            if category:
                stmt = stmt.where(JobFileORM.category == category.value)
            stmt = stmt.order_by(JobFileORM.created_at.asc())
            return list(db.execute(stmt).scalars().all())

    def get_job_file(self, file_id: int) -> JobFileORM | None:
        """按文件主键查询单个作业文件。
        参数:
        - file_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        with self._session_factory() as db:
            return db.get(JobFileORM, file_id)
