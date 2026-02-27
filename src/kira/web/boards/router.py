"""Board routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..deps import CurrentUser, Db, get_board_id_for_column, verify_board_access
from ..tasks import service as task_service
from . import service
from .models import (
    AddMemberRequest,
    BoardCreate,
    BoardResponse,
    BoardUpdate,
    CardBrief,
    ColumnCreate,
    ColumnReorder,
    ColumnResponse,
    ColumnUpdate,
    ColumnWithCards,
    CreateAndGenerateRequest,
    FullBoardResponse,
    GenerateCardsRequest,
    GeneratePlanResponse,
    MemberResponse,
    UpdateMemberRequest,
)

router = APIRouter(prefix="/api", tags=["boards"])


async def _get_active_board_plan(db, board_id: str) -> dict | None:
    """Return the active board_plan or card_gen task for a board, if any."""
    cursor = await db.execute(
        """SELECT * FROM tasks
           WHERE board_id = ? AND task_type IN ('board_plan', 'card_gen')
             AND status IN ('pending', 'claimed', 'running')
           ORDER BY created_at DESC LIMIT 1""",
        (board_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


# --- Board CRUD ---


@router.get("/boards", response_model=list[BoardResponse])
async def list_boards(user: CurrentUser, db: Db):
    return await service.list_boards(db, user["sub"])


@router.post("/boards", response_model=BoardResponse, status_code=201)
async def create_board(body: BoardCreate, user: CurrentUser, db: Db):
    board = await service.create_board(db, body.name, body.description, user["sub"])
    return board


@router.post("/boards/generate", response_model=GeneratePlanResponse, status_code=201)
async def create_and_generate(body: CreateAndGenerateRequest, user: CurrentUser, db: Db):
    """Create a new board from a natural language request and generate a plan."""
    # Use prompt's first ~50 chars as board name if none provided
    name = body.name.strip() if body.name.strip() else body.prompt[:50].strip()

    board = await service.create_board(db, name, "", user["sub"])

    import json

    task = await task_service.create_task(
        db,
        task_type="board_plan",
        board_id=board["id"],
        created_by=user["sub"],
        agent_type="architect",
        agent_model="smart",
        prompt_text=body.prompt,
        payload_json=json.dumps({"auto_generate_cards": True}),
    )

    return GeneratePlanResponse(board_id=board["id"], task_id=task["id"])


@router.post("/boards/{board_id}/generate", response_model=GeneratePlanResponse, status_code=201)
async def generate_cards(board_id: str, body: GenerateCardsRequest, user: CurrentUser, db: Db):
    """Generate cards for an existing board from a prompt."""
    await verify_board_access(db, board_id, user["sub"])
    board = await service.get_board(db, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")

    # Prevent duplicate generation tasks
    active = await _get_active_board_plan(db, board_id)
    if active:
        return GeneratePlanResponse(board_id=board_id, task_id=active["id"])

    # Determine target column: explicit, or auto-detect Plan/first column
    target_column_id = body.column_id
    if not target_column_id:
        col_cursor = await db.execute(
            """SELECT id, name FROM columns WHERE board_id = ?
               ORDER BY position ASC""",
            (board_id,),
        )
        columns = await col_cursor.fetchall()
        if columns:
            # Prefer column named "Plan", otherwise use first column
            target_column_id = columns[0]["id"]
            for col in columns:
                if col["name"].lower() == "plan":
                    target_column_id = col["id"]
                    break

    import json

    task = await task_service.create_task(
        db,
        task_type="card_gen",
        board_id=board_id,
        created_by=user["sub"],
        agent_type="architect",
        agent_model="smart",
        prompt_text=body.prompt,
        payload_json=json.dumps({"target_column_id": target_column_id}),
    )

    return GeneratePlanResponse(board_id=board_id, task_id=task["id"])


@router.get("/boards/{board_id}", response_model=FullBoardResponse)
async def get_board(board_id: str, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    result = await service.get_full_board(db, board_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Board not found")

    board = result["board"]
    columns = [
        ColumnWithCards(
            **{k: v for k, v in c.items() if k != "cards"},
            cards=[CardBrief(**card) for card in c["cards"]],
        )
        for c in result["columns"]
    ]
    members = [MemberResponse(**m) for m in result["members"]]

    return FullBoardResponse(
        board=BoardResponse(**board),
        columns=columns,
        members=members,
    )


@router.get("/boards/{board_id}/settings")
async def get_board_settings(board_id: str, user: CurrentUser, db: Db):
    """Return the parsed settings_json for a board."""
    await verify_board_access(db, board_id, user["sub"])
    import json

    board = await service.get_board(db, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    try:
        settings = json.loads(board.get("settings_json", "{}") or "{}")
    except json.JSONDecodeError:
        settings = {}
    return settings


@router.patch("/boards/{board_id}/settings")
async def update_board_settings(board_id: str, body: dict, user: CurrentUser, db: Db):
    """Merge-update board settings_json."""
    await verify_board_access(db, board_id, user["sub"])
    import json

    board = await service.get_board(db, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    try:
        current = json.loads(board.get("settings_json", "{}") or "{}")
    except json.JSONDecodeError:
        current = {}
    current.update(body)
    updated = await service.update_board(db, board_id, {"settings_json": json.dumps(current)})
    return updated


@router.patch("/boards/{board_id}", response_model=BoardResponse)
async def update_board(board_id: str, body: BoardUpdate, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    updates = body.model_dump(exclude_none=True)
    board = await service.update_board(db, board_id, updates)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(board_id: str, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    deleted = await service.delete_board(db, board_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Board not found")
    return Response(status_code=204)


# --- Column CRUD ---


@router.post("/boards/{board_id}/columns", response_model=ColumnResponse, status_code=201)
async def create_column(board_id: str, body: ColumnCreate, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    col = await service.create_column(db, board_id, body.model_dump())
    return col


@router.patch("/columns/{column_id}", response_model=ColumnResponse)
async def update_column(column_id: str, body: ColumnUpdate, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_column(db, column_id)
    await verify_board_access(db, board_id, user["sub"])
    updates = body.model_dump(exclude_none=True)
    col = await service.update_column(db, column_id, updates)
    if col is None:
        raise HTTPException(status_code=404, detail="Column not found")
    return col


@router.delete("/columns/{column_id}", status_code=204)
async def delete_column(column_id: str, user: CurrentUser, db: Db):
    board_id = await get_board_id_for_column(db, column_id)
    await verify_board_access(db, board_id, user["sub"])
    deleted = await service.delete_column(db, column_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Column not found")
    return Response(status_code=204)


@router.patch("/boards/{board_id}/columns/reorder")
async def reorder_columns(board_id: str, body: ColumnReorder, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    await service.reorder_columns(db, board_id, body.column_ids)
    return {"status": "ok"}


# --- Board member management ---


@router.get("/boards/{board_id}/members", response_model=list[MemberResponse])
async def list_members(board_id: str, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    return await service.get_members(db, board_id)


@router.post("/boards/{board_id}/members", status_code=201)
async def add_member(board_id: str, body: AddMemberRequest, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    # Verify the target user exists
    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (body.user_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
    added = await service.add_member(db, board_id, body.user_id, body.role)
    if not added:
        raise HTTPException(status_code=409, detail="User is already a member")
    return {"status": "added"}


@router.patch("/boards/{board_id}/members/{member_user_id}")
async def update_member(
    board_id: str, member_user_id: str, body: UpdateMemberRequest, user: CurrentUser, db: Db
):
    await verify_board_access(db, board_id, user["sub"])
    updated = await service.update_member_role(db, board_id, member_user_id, body.role)
    if not updated:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"status": "updated"}


@router.delete("/boards/{board_id}/members/{member_user_id}", status_code=204)
async def remove_member(board_id: str, member_user_id: str, user: CurrentUser, db: Db):
    await verify_board_access(db, board_id, user["sub"])
    removed = await service.remove_member(db, board_id, member_user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return Response(status_code=204)
