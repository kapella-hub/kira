"""GitLab routes - read-only operations are server-proxied, writes go through worker tasks."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query

from ..deps import CurrentUser, Db, verify_board_access
from ..tasks import service as task_service
from .models import (
    CreateProjectRequest,
    GitLabNamespaceInfo,
    GitLabProjectInfo,
    GitLabPushRequest,
    GitLabTaskResponse,
    GitLabTestResponse,
    LinkProjectRequest,
)

router = APIRouter(prefix="/api/gitlab", tags=["gitlab"])


async def _get_gitlab_client(db, user_id: str):
    """Load GitLab credentials from DB and create a client.

    Raises HTTPException if credentials are not configured.
    """
    from kira.integrations.gitlab.client import GitLabClient

    cursor = await db.execute(
        "SELECT gitlab_server, gitlab_token_encrypted FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row or not row["gitlab_server"] or not row["gitlab_token_encrypted"]:
        raise HTTPException(
            status_code=400,
            detail="GitLab credentials not configured. Update your GitLab settings first.",
        )

    return GitLabClient(row["gitlab_server"], row["gitlab_token_encrypted"])


@router.post("/credentials")
async def save_gitlab_credentials_alias(body: dict, user: CurrentUser, db: Db):
    """Save GitLab credentials (alias for /api/auth/users/me/gitlab)."""
    server = body.get("server", "")
    token = body.get("token", "")
    await db.execute(
        "UPDATE users SET gitlab_server = ?, gitlab_token_encrypted = ? WHERE id = ?",
        (server, token, user["sub"]),
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/status")
async def gitlab_status_alias(user: CurrentUser, db: Db):
    """Check if GitLab credentials are configured."""
    cursor = await db.execute(
        "SELECT gitlab_server, gitlab_token_encrypted FROM users WHERE id = ?",
        (user["sub"],),
    )
    row = await cursor.fetchone()
    if not row:
        return {"configured": False, "server": ""}
    configured = bool(row["gitlab_server"] and row["gitlab_token_encrypted"])
    return {"configured": configured, "server": row["gitlab_server"] or ""}


@router.post("/test-connection", response_model=GitLabTestResponse)
async def test_connection(user: CurrentUser, db: Db):
    """Test GitLab connection using stored credentials."""
    try:
        client = await _get_gitlab_client(db, user["sub"])
        user_info = await asyncio.to_thread(client.test_connection)
        return GitLabTestResponse(
            success=True,
            username=user_info.get("username", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        return GitLabTestResponse(success=False, error=str(e))


@router.get("/projects", response_model=list[GitLabProjectInfo])
async def list_projects(
    user: CurrentUser,
    db: Db,
    search: str = Query(default="", description="Search term to filter projects"),
):
    """List GitLab projects the user is a member of."""
    client = await _get_gitlab_client(db, user["sub"])
    projects = await asyncio.to_thread(client.list_projects, search)
    return [
        GitLabProjectInfo(
            id=p["id"],
            name=p["name"],
            path_with_namespace=p.get("path_with_namespace", ""),
            web_url=p.get("web_url", ""),
            default_branch=p.get("default_branch", "main") or "main",
        )
        for p in projects
    ]


@router.get("/namespaces", response_model=list[GitLabNamespaceInfo])
async def list_namespaces(user: CurrentUser, db: Db):
    """List GitLab namespaces available to the user."""
    client = await _get_gitlab_client(db, user["sub"])
    namespaces = await asyncio.to_thread(client.list_namespaces)
    return [
        GitLabNamespaceInfo(
            id=ns["id"],
            name=ns["name"],
            path=ns.get("path", ""),
            kind=ns.get("kind", ""),
        )
        for ns in namespaces
    ]


@router.post("/link-project")
async def link_project(body: LinkProjectRequest, user: CurrentUser, db: Db):
    """Link a GitLab project to a board (direct DB write, no task)."""
    await verify_board_access(db, body.board_id, user["sub"])
    from ..boards.service import get_board

    board = await get_board(db, body.board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    # Update board settings_json with gitlab project info
    settings = json.loads(board.get("settings_json", "{}") or "{}")
    settings["gitlab"] = {
        "project_id": body.project_id,
        "project_path": body.project_path,
        "project_url": body.project_url,
        "default_branch": body.default_branch,
        "auto_push": body.auto_push,
        "push_on_complete": body.push_on_complete,
    }

    await db.execute(
        "UPDATE boards SET settings_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(settings), body.board_id),
    )
    await db.commit()

    return {"status": "ok", "message": f"Linked GitLab project {body.project_path} to board"}


@router.post("/create-project", response_model=GitLabTaskResponse, status_code=201)
async def create_project(body: CreateProjectRequest, user: CurrentUser, db: Db):
    """Create a gitlab_create_project task for the worker."""
    await verify_board_access(db, body.board_id, user["sub"])
    payload = json.dumps(
        {
            "name": body.name,
            "namespace_id": body.namespace_id,
            "visibility": body.visibility,
            "description": body.description,
            "board_id": body.board_id,
            "auto_push": body.auto_push,
            "push_on_complete": body.push_on_complete,
        }
    )

    task = await task_service.create_task(
        db,
        task_type="gitlab_create_project",
        board_id=body.board_id,
        created_by=user["sub"],
        assigned_to=user["sub"],
        payload_json=payload,
    )
    return GitLabTaskResponse(
        task_id=task["id"],
        status=task["status"],
        message="GitLab project creation task queued.",
    )


@router.post("/push/{card_id}", response_model=GitLabTaskResponse, status_code=201)
async def push_to_gitlab(
    card_id: str,
    body: GitLabPushRequest,
    user: CurrentUser,
    db: Db,
):
    """Create a gitlab_push task for the worker."""
    from ..cards.service import get_card

    card = await get_card(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    await verify_board_access(db, card["board_id"], user["sub"])

    # Load board settings to get gitlab project info
    board_cursor = await db.execute(
        "SELECT settings_json FROM boards WHERE id = ?", (card["board_id"],)
    )
    board_row = await board_cursor.fetchone()
    if not board_row:
        raise HTTPException(status_code=404, detail="Board not found")

    settings = json.loads(board_row["settings_json"] or "{}")
    gitlab_settings = settings.get("gitlab", {})
    if not gitlab_settings.get("project_id"):
        raise HTTPException(
            status_code=400,
            detail="No GitLab project linked to this board",
        )

    payload = json.dumps(
        {
            "project_id": gitlab_settings["project_id"],
            "project_path": gitlab_settings.get("project_path", ""),
            "default_branch": gitlab_settings.get("default_branch", "main"),
            "mr_prefix": gitlab_settings.get("mr_prefix", "kira/"),
            "card_title": card["title"],
            "branch_name": body.branch_name,
            "commit_message": body.commit_message or f"feat: {card['title']}",
            "create_mr": body.create_mr,
            "mr_title": body.mr_title or card["title"],
        }
    )

    task = await task_service.create_task(
        db,
        task_type="gitlab_push",
        board_id=card["board_id"],
        card_id=card_id,
        created_by=user["sub"],
        assigned_to=user["sub"],
        payload_json=payload,
    )
    return GitLabTaskResponse(
        task_id=task["id"],
        status=task["status"],
        message="GitLab push task queued.",
    )
