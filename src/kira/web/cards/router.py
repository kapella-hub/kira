"""Card routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..deps import (
    CurrentUser,
    Db,
    get_board_id_for_card,
    get_board_id_for_column,
    get_board_id_for_comment,
    verify_board_access,
)
from . import service
from .models import (
    CardCreate,
    CardMove,
    CardReorder,
    CardResponse,
    CardUpdate,
    CommentCreate,
    CommentResponse,
)

router = APIRouter(prefix="/api", tags=["cards"])


# --- Card CRUD ---


@router.get("/cards/{card_id}", response_model=CardResponse)
async def get_card(card_id: str, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])
    card = await service.get_card(db, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.post("/cards", response_model=CardResponse, status_code=201)
async def create_card(body: CardCreate, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_column(db, body.column_id)
    await verify_board_access(db, board_id, user["sub"])
    try:
        card = await service.create_card(
            db,
            column_id=body.column_id,
            title=body.title,
            user_id=user["sub"],
            description=body.description,
            assignee_id=body.assignee_id,
            priority=body.priority,
            labels=body.labels,
            due_date=body.due_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return card


@router.patch("/cards/{card_id}", response_model=CardResponse)
async def update_card(card_id: str, body: CardUpdate, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])
    updates = body.model_dump(exclude_none=True)

    # Check card lock — but allow agent_status-only updates (system-initiated)
    existing = await service.get_card(db, card_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if service.is_card_locked(existing) and set(updates.keys()) != {"agent_status"}:
        raise HTTPException(
            status_code=409,
            detail="Card is locked while agent is working on it",
        )

    card = await service.update_card(db, card_id, updates)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(card_id: str, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])

    existing = await service.get_card(db, card_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if service.is_card_locked(existing):
        raise HTTPException(
            status_code=409,
            detail="Card is locked while agent is working on it",
        )

    deleted = await service.delete_card(db, card_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Card not found")
    return Response(status_code=204)


@router.post("/cards/{card_id}/move", response_model=CardResponse)
async def move_card(card_id: str, body: CardMove, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])

    existing = await service.get_card(db, card_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if service.is_card_locked(existing):
        raise HTTPException(
            status_code=409,
            detail="Card is locked while agent is working on it",
        )

    card = await service.move_card(db, card_id, body.column_id, body.position, user["sub"])
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.post("/cards/reorder")
async def reorder_cards(body: CardReorder, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_column(db, body.column_id)
    await verify_board_access(db, board_id, user["sub"])
    await service.reorder_cards(db, body.column_id, body.card_ids)
    return {"status": "ok"}


# --- Comments ---


@router.get("/cards/{card_id}/comments", response_model=list[CommentResponse])
async def get_comments(card_id: str, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])
    comments = await service.get_comments(db, card_id)
    return [
        CommentResponse(**{**c, "is_agent_output": bool(c["is_agent_output"])}) for c in comments
    ]


@router.post("/cards/{card_id}/comments", response_model=CommentResponse, status_code=201)
async def create_comment(card_id: str, body: CommentCreate, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_card(db, card_id)
    await verify_board_access(db, board_id, user["sub"])
    comment = await service.create_comment(db, card_id, user["sub"], body.content)
    comment["is_agent_output"] = bool(comment["is_agent_output"])
    return comment


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_comment(db, comment_id)
    await verify_board_access(db, board_id, user["sub"])
    deleted = await service.delete_comment(db, comment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
    return Response(status_code=204)
