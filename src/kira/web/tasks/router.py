"""Task routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import CurrentUser, Db, verify_board_access
from . import service
from .models import TaskResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    user: CurrentUser,
    db: Db,
    board_id: str | None = None,
    card_id: str | None = None,
    status: str | None = None,
):
    if board_id:
        await verify_board_access(db, board_id, user["sub"])
    tasks = await service.get_tasks(db, board_id=board_id, card_id=card_id, status=status)
    return tasks


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, user: CurrentUser, db: Db):
    task = await service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await verify_board_access(db, task["board_id"], user["sub"])
    try:
        task = await service.cancel_task(db, task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"status": "cancelled"}
