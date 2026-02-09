"""P1 回归测试：覆盖哈希一致性、终态保护与产物访问边界行为。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.orchestrator import OrchestratorService, UploadedFileData
from app.config import Settings
from app.domain.enums import JobStatus
from app.infra.db.models import Base
from app.infra.db.repository import JobRepository


def test_requirement_hash_uses_file_content() -> None:
    """验证需求哈希包含文件内容，内容变化会导致哈希变化。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    files_a = [UploadedFileData(filename="data.csv", content=b"a,b\n1,2\n", content_type="text/csv")]
    files_b = [UploadedFileData(filename="data.csv", content=b"a,b\n9,9\n", content_type="text/csv")]

    hash_a = OrchestratorService._build_requirement_hash("analyze this", files_a)
    hash_b = OrchestratorService._build_requirement_hash("analyze this", files_b)

    assert hash_a != hash_b


def test_status_cannot_override_aborted(tmp_path: Path) -> None:
    """验证作业进入 aborted 后不能被其他状态覆盖。
    参数:
    - tmp_path: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    db_path = tmp_path / "repo.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    repo = JobRepository(session_factory)

    repo.create_job(
        job_id="job-1",
        tenant_id="default",
        workspace_dir=str(tmp_path / "job-1"),
        requirement_text="test",
        selected_skill="general-default",
        agent="build",
        model_json=None,
        output_contract_json=None,
        created_by="tester",
        input_files=[],
        idempotency_key=None,
        requirement_hash="abc",
    )

    repo.set_status("job-1", JobStatus.aborted)
    changed = repo.set_status("job-1", JobStatus.succeeded)
    job = repo.get_job("job-1")

    assert changed is False
    assert job is not None
    assert job.status == JobStatus.aborted.value


@dataclass
class _DummyJobFile:
    """测试用作业文件桩对象。"""
    id: int
    job_id: str
    category: str
    relative_path: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    created_at: datetime


@dataclass
class _DummyJob:
    """测试用作业桩对象。"""
    id: str
    workspace_dir: str


class _RepoStub:
    """测试用仓储桩，提供最小查询行为。"""
    def __init__(self, files: list[_DummyJobFile], job: _DummyJob) -> None:
        """__init__ 函数实现业务步骤并返回处理结果。
        参数:
        - files: 业务参数，具体语义见调用上下文。
        - job: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._files = files
        self._job = job

    def list_job_files(self, _job_id: str) -> list[_DummyJobFile]:
        """查询作业文件列表，可按类别过滤。
        参数:
        - _job_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return self._files

    def get_job_file(self, file_id: int) -> _DummyJobFile | None:
        """按文件主键查询单个作业文件。
        参数:
        - file_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        for item in self._files:
            if item.id == file_id:
                return item
        return None

    def get_job(self, _job_id: str) -> _DummyJob:
        """查询作业详情并返回下载链接等视图字段。
        参数:
        - _job_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        return self._job


def _build_service(repo_stub: _RepoStub, tmp_path: Path) -> OrchestratorService:
    """构造最小 OrchestratorService 测试实例。
    参数:
    - repo_stub: 业务参数，具体语义见调用上下文。
    - tmp_path: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    settings = Settings(data_root=tmp_path / "data")
    return OrchestratorService(
        settings=settings,
        repository=repo_stub,  # type: ignore[arg-type]
        skill_registry=None,  # type: ignore[arg-type]
        skill_router=None,  # type: ignore[arg-type]
        workspace_manager=None,  # type: ignore[arg-type]
        artifact_manager=None,  # type: ignore[arg-type]
        opencode_client=None,  # type: ignore[arg-type]
    )


def test_artifact_list_filters_to_output_and_bundle(tmp_path: Path) -> None:
    """验证产物列表仅返回 output 与 bundle 类别。
    参数:
    - tmp_path: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    now = datetime.now(timezone.utc)
    files = [
        _DummyJobFile(1, "job-1", "input", "inputs/raw.csv", "text/csv", 10, "x", now),
        _DummyJobFile(2, "job-1", "output", "outputs/report.md", "text/markdown", 11, "y", now),
        _DummyJobFile(3, "job-1", "bundle", "bundle/result.zip", "application/zip", 12, "z", now),
        _DummyJobFile(4, "job-1", "log", "logs/opencode-last-message.md", "text/markdown", 13, "w", now),
    ]
    repo = _RepoStub(files, _DummyJob(id="job-1", workspace_dir=str(tmp_path / "job-1")))
    service = _build_service(repo, tmp_path)

    result = service.list_artifacts("job-1")

    assert [item["category"] for item in result] == ["output", "bundle"]


def test_artifact_download_rejects_non_output_and_non_bundle(tmp_path: Path) -> None:
    """验证非可下载类别文件无法通过下载接口访问。
    参数:
    - tmp_path: 业务参数，具体语义见调用上下文。
    返回:
    - 按函数签名返回对应结果；异常场景会抛出业务异常。
    """
    workspace = tmp_path / "job-1"
    (workspace / "inputs").mkdir(parents=True, exist_ok=True)
    (workspace / "inputs" / "raw.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    now = datetime.now(timezone.utc)
    files = [
        _DummyJobFile(1, "job-1", "input", "inputs/raw.csv", "text/csv", 10, "x", now),
    ]
    repo = _RepoStub(files, _DummyJob(id="job-1", workspace_dir=str(workspace)))
    service = _build_service(repo, tmp_path)

    with pytest.raises(FileNotFoundError):
        service.get_artifact_path("job-1", 1)
