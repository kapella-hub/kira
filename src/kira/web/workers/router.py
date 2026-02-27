"""Worker routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import CurrentUser, Db
from ..tasks import service as task_service
from ..tasks.models import TaskClaim, TaskComplete, TaskFail, TaskProgress, TaskResponse
from . import service
from .models import HeartbeatResponse, WorkerHeartbeat, WorkerInfo, WorkerRegister, WorkerResponse

router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.post("/register", response_model=WorkerResponse, status_code=201)
async def register_worker(body: WorkerRegister, user: CurrentUser, db: Db):
    worker = await service.register_worker(
        db,
        user_id=user["sub"],
        hostname=body.hostname,
        worker_version=body.worker_version,
        capabilities=body.capabilities,
    )
    return WorkerResponse(
        worker_id=worker["id"],
        max_concurrent_tasks=1,
        poll_interval_seconds=5,
        heartbeat_interval_seconds=30,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(body: WorkerHeartbeat, user: CurrentUser, db: Db):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, body.worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    result = await service.heartbeat(
        db,
        worker_id=body.worker_id,
        user_id=user["sub"],
        running_task_ids=body.running_task_ids,
    )
    return HeartbeatResponse(
        status=result["status"],
        cancel_task_ids=result["cancel_task_ids"],
    )


@router.get("/tasks/poll", response_model=list[TaskResponse])
async def poll_tasks(worker_id: str, user: CurrentUser, db: Db, limit: int = 1):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    tasks = await task_service.poll_tasks(db, user_id=user["sub"], limit=limit)
    return tasks


@router.post("/tasks/{task_id}/claim")
async def claim_task(task_id: str, body: TaskClaim, user: CurrentUser, db: Db):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, body.worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    task = await task_service.claim_task(db, task_id, body.worker_id)
    if task is None:
        raise HTTPException(status_code=409, detail="Task already claimed")
    return {"status": "claimed", "task": task}


@router.post("/tasks/{task_id}/progress")
async def report_progress(task_id: str, body: TaskProgress, user: CurrentUser, db: Db):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, body.worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    task = await task_service.update_progress(
        db,
        task_id,
        body.progress_text,
        step=body.step,
        total_steps=body.total_steps,
        phase=body.phase,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: TaskComplete, user: CurrentUser, db: Db):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, body.worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    try:
        task = await task_service.complete_task(
            db, task_id, output_text=body.output_text, result_data=body.result_data
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    return {
        "status": task["status"],
        "next_action": task.get("next_action"),
    }


@router.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, body: TaskFail, user: CurrentUser, db: Db):
    # Verify worker belongs to this user
    worker = await service.get_worker(db, body.worker_id)
    if not worker or worker["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Worker does not belong to this user")

    try:
        task = await task_service.fail_task(
            db, task_id, error_summary=body.error_summary, output_text=body.output_text
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    return {
        "status": task["status"],
        "next_action": task.get("next_action"),
    }


@router.get("", response_model=list[WorkerInfo])
async def list_workers(user: CurrentUser, db: Db):
    workers = await service.get_workers(db)
    return workers
