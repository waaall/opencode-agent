"""任务执行器核心流程：驱动 OpenCode 执行、处理权限、校验输出并打包归档。"""

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
    """作业被外部中止时抛出的内部控制异常。"""
    pass


class JobExecutor:
    """任务执行器，负责完整驱动单个作业从运行到归档完成。"""
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
        """__init__ 函数实现业务步骤并返回处理结果。
        参数:
        - settings: 业务参数，具体语义见调用上下文。
        - repository: 业务参数，具体语义见调用上下文。
        - skill_registry: 业务参数，具体语义见调用上下文。
        - workspace_manager: 业务参数，具体语义见调用上下文。
        - artifact_manager: 业务参数，具体语义见调用上下文。
        - opencode_client: 业务参数，具体语义见调用上下文。
        - event_bridge: 业务参数，具体语义见调用上下文。
        - permission_policy: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        self._settings = settings
        self._repository = repository
        self._skill_registry = skill_registry
        self._workspace_manager = workspace_manager
        self._artifact_manager = artifact_manager
        self._opencode_client = opencode_client
        self._event_bridge = event_bridge
        self._permission_policy = permission_policy

    def run(self, job_id: str) -> None:
        """执行作业主流程，包括调用模型、校验输出与归档产物。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if job.status == JobStatus.aborted.value:
            # 任务已在入队前被取消时直接跳过，避免创建无效会话。
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

            # 执行计划由创建阶段落盘，此处按同一快照构造提示词，保证可追溯性。
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
            # 在验收前校验输入是否被意外改写，防止模型篡改原始数据。
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
                # 输出文件按路径幂等 upsert，支持重跑覆盖而不重复插入记录。
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
                # 日志为可选产物，不影响主流程成功判定。
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
        """等待 OpenCode 会话完成，期间同步事件与权限状态。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        deadline = time.monotonic() + self._settings.job_soft_timeout_seconds
        approval_wait_started_at: float | None = None
        last_status_poll = 0.0

        while time.monotonic() < deadline:
            self._ensure_not_aborted(job_id, workspace_dir, session_id)
            now = time.monotonic()
            if now - last_status_poll >= 2:
                # 即使没有流式事件，也定期拉状态避免遗漏终态。
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
                        # 观测到 permission 事件时立即处理，缩短等待时长。
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
                # SSE 窗口超时并不代表失败，后续通过状态轮询补偿。
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
            # 超时后主动终止远端会话，避免后台继续消耗资源。
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
        """同步会话状态与审批状态，判断作业是否完成。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        - approval_wait_started_at: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
                # 首次进入审批等待态时更新状态，方便前端实时展示。
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
        """筛选并落库存储关键流式事件。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - event: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
        """规范化事件数据为可序列化字典。
        参数:
        - data: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        if data is None:
            return None
        if isinstance(data, dict):
            return data
        return {"data": data}

    def _process_permissions(self, job_id: str, workspace_dir: Path) -> None:
        """拉取并自动回复待审批权限请求。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        permissions = self._opencode_client.list_permissions(workspace_dir)
        for request in permissions:
            request_id = str(request.get("id", ""))
            if not request_id:
                # 请求缺少 ID 无法回执，直接忽略避免回复错误目标。
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
        """校验输入文件哈希，确保执行过程中未被篡改。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        input_files = self._repository.list_job_files(job_id, FileCategory.input)
        for file_meta in input_files:
            path = workspace_dir / file_meta.relative_path
            if not path.exists():
                raise ValueError(f"input file missing: {file_meta.relative_path}")
            current_sha = sha256_file(path)
            # 通过哈希比对确保输入数据在执行期间未被篡改。
            if current_sha != file_meta.sha256:
                raise ValueError(f"input file modified unexpectedly: {file_meta.relative_path}")

    def _set_status_or_abort(self, job_id: str, status: JobStatus) -> None:
        """尝试更新状态；若作业已中止则抛出中止异常。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - status: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
        changed = self._repository.set_status(job_id, status)
        if not changed:
            raise JobAbortedError("job was aborted")

    def _ensure_not_aborted(self, job_id: str, workspace_dir: Path, session_id: str | None = None) -> None:
        """检查作业是否已中止，并在必要时向 OpenCode 发送中止。
        参数:
        - job_id: 业务参数，具体语义见调用上下文。
        - workspace_dir: 业务参数，具体语义见调用上下文。
        - session_id: 业务参数，具体语义见调用上下文。
        返回:
        - 按函数签名返回对应结果；异常场景会抛出业务异常。
        """
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
