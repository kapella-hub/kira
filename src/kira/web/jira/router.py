"""Jira task routes - creates tasks for worker execution."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..deps import CurrentUser, Db, verify_board_access
from ..tasks import service as task_service
from .models import JiraImportRequest, JiraTaskResponse

router = APIRouter(prefix="/api/jira", tags=["jira"])


@router.post("/import", response_model=JiraTaskResponse, status_code=201)
async def import_issues(body: JiraImportRequest, user: CurrentUser, db: Db):
    """Create a jira_import task for the worker to execute."""
    await verify_board_access(db, body.board_id, user["sub"])
    payload = json.dumps(
        {
            "jql": body.jql,
            "board_id": body.board_id,
            "column_id": body.column_id,
        }
    )

    task = await task_service.create_task(
        db,
        task_type="jira_import",
        board_id=body.board_id,
        created_by=user["sub"],
        assigned_to=user["sub"],
        payload_json=payload,
    )
    return JiraTaskResponse(
        task_id=task["id"],
        status=task["status"],
        message="Jira import task queued. Your worker will execute it.",
    )


@router.post("/push/{card_id}", response_model=JiraTaskResponse, status_code=201)
async def push_to_jira(card_id: str, user: CurrentUser, db: Db):
    """Create a jira_push task for the worker to execute."""
    from ..cards.service import get_card

    card = await get_card(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    await verify_board_access(db, card["board_id"], user["sub"])

    payload = json.dumps({"card_id": card_id})

    task = await task_service.create_task(
        db,
        task_type="jira_push",
        board_id=card["board_id"],
        card_id=card_id,
        created_by=user["sub"],
        assigned_to=user["sub"],
        payload_json=payload,
    )
    return JiraTaskResponse(
        task_id=task["id"],
        status=task["status"],
        message="Jira push task queued.",
    )


@router.post("/sync/{board_id}", response_model=JiraTaskResponse, status_code=201)
async def sync_board(board_id: str, user: CurrentUser, db: Db):
    """Create a jira_sync task for the worker to execute."""
    await verify_board_access(db, board_id, user["sub"])
    from ..boards.service import get_board

    board = await get_board(db, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    payload = json.dumps({"board_id": board_id})

    task = await task_service.create_task(
        db,
        task_type="jira_sync",
        board_id=board_id,
        created_by=user["sub"],
        assigned_to=user["sub"],
        payload_json=payload,
    )
    return JiraTaskResponse(
        task_id=task["id"],
        status=task["status"],
        message="Jira sync task queued.",
    )
