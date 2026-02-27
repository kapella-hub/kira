"""Search routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..deps import CurrentUser, Db, verify_board_access
from . import service

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    board_id: str = Query(..., description="Board ID to search within"),
    user: CurrentUser = None,
    db: Db = None,
):
    """Hybrid vector + FTS search for cards within a specific board."""
    await verify_board_access(db, board_id, user["sub"])
    results = await service.search(db, q, board_id=board_id)
    return results
