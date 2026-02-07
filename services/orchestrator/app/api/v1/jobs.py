from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.v1.schemas import ArtifactItem, ArtifactListResponse, JobCreateResponse, JobDetailResponse, JobStartResponse
from app.application.container import get_orchestrator_service
from app.application.orchestrator import OrchestratorService, UploadedFileData
from app.domain.enums import JobStatus

router = APIRouter()


def _service() -> OrchestratorService:
    return get_orchestrator_service()


@router.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    requirement: Annotated[str, Form(...)],
    files: Annotated[list[UploadFile], File(...)],
    skill_code: Annotated[str | None, Form()] = None,
    agent: Annotated[str | None, Form()] = None,
    model_provider_id: Annotated[str | None, Form()] = None,
    model_id: Annotated[str | None, Form()] = None,
    output_contract: Annotated[str | None, Form()] = None,
    idempotency_key: Annotated[str | None, Form()] = None,
    orchestrator: OrchestratorService = Depends(_service),
) -> JobCreateResponse:
    try:
        parsed_output_contract = json.loads(output_contract) if output_contract else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid output_contract JSON: {exc}") from exc

    if bool(model_provider_id) != bool(model_id):
        raise HTTPException(
            status_code=400,
            detail="model_provider_id and model_id must be provided together",
        )
    model = {"providerID": model_provider_id, "modelID": model_id} if model_provider_id and model_id else None

    uploaded_files: list[UploadedFileData] = []
    for item in files:
        content = await item.read()
        uploaded_files.append(
            UploadedFileData(
                filename=item.filename or "upload.bin",
                content=content,
                content_type=item.content_type,
            )
        )

    try:
        job = await asyncio.to_thread(
            orchestrator.create_job,
            requirement=requirement,
            files=uploaded_files,
            skill_code=skill_code,
            agent=agent,
            model=model,
            output_contract=parsed_output_contract,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobCreateResponse(job_id=job.id, status=job.status, selected_skill=job.selected_skill)


@router.post("/jobs/{job_id}/start", response_model=JobStartResponse)
def start_job(
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> JobStartResponse:
    try:
        job = orchestrator.start_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"unable to enqueue job: {exc}") from exc
    return JobStartResponse(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> JobDetailResponse:
    try:
        job = orchestrator.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    download_url = f"/api/v1/jobs/{job.id}/download" if job.result_bundle_path else None
    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        session_id=job.session_id,
        selected_skill=job.selected_skill,
        agent=job.agent,
        model=job.model_json,
        error_code=job.error_code,
        error_message=job.error_message,
        download_url=download_url,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/{job_id}/events")
async def job_events(
    request: Request,
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> StreamingResponse:
    try:
        await asyncio.to_thread(orchestrator.get_job, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    terminal_states = {JobStatus.succeeded.value, JobStatus.failed.value, JobStatus.aborted.value}

    async def event_stream() -> Any:
        last_id = 0
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            events = await asyncio.to_thread(orchestrator.list_job_events, job_id, last_id, 200)
            if events:
                idle_ticks = 0
            for event in events:
                last_id = max(last_id, int(event["id"]))
                payload = {
                    "job_id": event["job_id"],
                    "status": event["status"],
                    "source": event["source"],
                    "event_type": event["event_type"],
                    "message": event["message"],
                    "payload": event["payload"],
                    "created_at": event["created_at"].isoformat() if event["created_at"] else None,
                }
                yield f"event: {event['event_type']}\n"
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if not events:
                idle_ticks += 1
                yield ": keep-alive\n\n"

            job = await asyncio.to_thread(orchestrator.get_job, job_id)
            if job.status in terminal_states and idle_ticks >= 2:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/abort", response_model=JobDetailResponse)
def abort_job(
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> JobDetailResponse:
    try:
        job = orchestrator.abort_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"abort failed: {exc}") from exc
    return JobDetailResponse(
        job_id=job.id,
        status=job.status,
        session_id=job.session_id,
        selected_skill=job.selected_skill,
        agent=job.agent,
        model=job.model_json,
        error_code=job.error_code,
        error_message=job.error_message,
        download_url=f"/api/v1/jobs/{job.id}/download" if job.result_bundle_path else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> ArtifactListResponse:
    try:
        artifacts = orchestrator.list_artifacts(job_id)
        job = orchestrator.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    artifact_items = [ArtifactItem(**item) for item in artifacts]
    return ArtifactListResponse(job_id=job_id, artifacts=artifact_items, bundle_ready=bool(job.result_bundle_path))


@router.get("/jobs/{job_id}/download")
def download_bundle(
    job_id: str,
    orchestrator: OrchestratorService = Depends(_service),
) -> FileResponse:
    try:
        bundle_path = orchestrator.get_bundle_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=bundle_path, filename="result.zip", media_type="application/zip")


@router.get("/jobs/{job_id}/artifacts/{artifact_id}/download")
def download_single_artifact(
    job_id: str,
    artifact_id: int,
    orchestrator: OrchestratorService = Depends(_service),
) -> FileResponse:
    try:
        artifact_path = orchestrator.get_artifact_path(job_id, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path=artifact_path, filename=artifact_path.name)
