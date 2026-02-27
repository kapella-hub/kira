"""Auth routes."""

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, HTTPException

from ..boards.service import add_user_to_all_boards
from ..deps import CurrentUser, Db
from .models import (
    AuthConfigResponse,
    GitLabCredentialsStatus,
    GitLabCredentialsUpdate,
    JiraCredentialsUpdate,
    LoginRequest,
    ProfileUpdate,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from .service import create_token, get_provider

router = APIRouter(prefix="/api/auth", tags=["auth"])


DEMO_USERS = ["alice", "bob", "charlie"]


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config():
    """Public endpoint: returns auth mode and demo user list.

    Frontend uses this to decide whether to show password field,
    demo user buttons, etc.
    """
    provider = get_provider()
    return AuthConfigResponse(
        auth_mode=provider.mode,
        demo_users=DEMO_USERS if provider.mode == "mock" else [],
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Db):
    """Authenticate via configured provider and return JWT."""
    provider = get_provider()

    try:
        auth_result = await provider.authenticate(body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from None

    normalized_username = auth_result.username

    if provider.mode == "centauth" and auth_result.external_sub:
        # CentAuth mode: look up by centauth_sub first
        cursor = await db.execute(
            "SELECT id, username, display_name, avatar_url FROM users WHERE centauth_sub = ?",
            (auth_result.external_sub,),
        )
        row = await cursor.fetchone()

        if row is None:
            # Check if user exists by username (migration from mock -> centauth)
            cursor = await db.execute(
                "SELECT id, username, display_name, avatar_url FROM users "
                "WHERE LOWER(username) = ?",
                (normalized_username,),
            )
            row = await cursor.fetchone()

            if row:
                # Link existing user to centauth_sub
                await db.execute(
                    "UPDATE users SET centauth_sub = ?, display_name = ? WHERE id = ?",
                    (auth_result.external_sub, auth_result.display_name, row["id"]),
                )
                await db.commit()
            else:
                # Create new user
                user_id = secrets.token_hex(8)
                await db.execute(
                    "INSERT INTO users (id, username, display_name, centauth_sub) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        user_id,
                        normalized_username,
                        auth_result.display_name,
                        auth_result.external_sub,
                    ),
                )
                await db.commit()
                row = {
                    "id": user_id,
                    "username": normalized_username,
                    "display_name": auth_result.display_name,
                    "avatar_url": "",
                }
        else:
            # Update display name on each login
            await db.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (auth_result.display_name, row["id"]),
            )
            await db.commit()

    else:
        # Mock mode: find or create by username
        cursor = await db.execute(
            "SELECT id, username, display_name, avatar_url FROM users WHERE LOWER(username) = ?",
            (normalized_username,),
        )
        row = await cursor.fetchone()

        if row is None:
            user_id = secrets.token_hex(8)
            display_name = auth_result.display_name or normalized_username.capitalize()
            await db.execute(
                "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
                (user_id, normalized_username, display_name),
            )
            await db.commit()
            row = {
                "id": user_id,
                "username": normalized_username,
                "display_name": display_name,
                "avatar_url": "",
            }

    user = UserResponse(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
    )

    # Auto-share: ensure user is a member of all existing boards
    await add_user_to_all_boards(db, user.id)

    token = create_token(user.id, user.username)

    response = TokenResponse(token=token, user=user)
    # In CentAuth mode, we could also return refresh token info,
    # but for now we issue our own JWTs
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: Db):
    """Refresh an expired token using a refresh token (CentAuth only)."""
    provider = get_provider()

    if provider.mode != "centauth":
        raise HTTPException(status_code=400, detail="Token refresh not available in mock mode")

    try:
        token_pair = await provider.refresh(body.refresh_token)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=401, detail=str(e)) from None

    # Decode the new CentAuth token to find the user
    token_data = await provider.validate_external_token(token_pair.access_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid refreshed token")

    external_sub = token_data.get("sub", "")
    cursor = await db.execute(
        "SELECT id, username, display_name, avatar_url FROM users WHERE centauth_sub = ?",
        (external_sub,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    user = UserResponse(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
    )

    # Issue our own JWT
    kira_token = create_token(user.id, user.username)
    return TokenResponse(token=kira_token, user=user)


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser, db: Db):
    """Get current user profile."""
    cursor = await db.execute(
        "SELECT id, username, display_name, avatar_url FROM users WHERE id = ?",
        (user["sub"],),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
    )


@router.patch("/users/me/profile")
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: Db):
    """Update current user's profile and preferences."""
    updates: list[str] = []
    values: list[str] = []
    if body.display_name is not None:
        updates.append("display_name = ?")
        values.append(body.display_name)
    if body.avatar_url is not None:
        updates.append("avatar_url = ?")
        values.append(body.avatar_url)
    if body.preferences is not None:
        updates.append("preferences_json = ?")
        values.append(json.dumps(body.preferences))
    if not updates:
        return {"status": "ok"}
    values.append(user["sub"])
    await db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
    await db.commit()
    return {"status": "ok"}


@router.get("/users/me/preferences")
async def get_preferences(user: CurrentUser, db: Db):
    """Get current user's preferences."""
    cursor = await db.execute("SELECT preferences_json FROM users WHERE id = ?", (user["sub"],))
    row = await cursor.fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["preferences_json"] or "{}")
    except json.JSONDecodeError:
        return {}


@router.patch("/users/me/jira")
async def update_jira_credentials(body: JiraCredentialsUpdate, user: CurrentUser, db: Db):
    """Store per-user Jira credentials."""
    await db.execute(
        """UPDATE users SET jira_server = ?, jira_username = ?, jira_token_encrypted = ?
           WHERE id = ?""",
        (body.server, body.username, body.token, user["sub"]),
    )
    await db.commit()
    return {"status": "ok"}


@router.patch("/users/me/gitlab")
async def update_gitlab_credentials(body: GitLabCredentialsUpdate, user: CurrentUser, db: Db):
    """Store per-user GitLab credentials."""
    await db.execute(
        """UPDATE users SET gitlab_server = ?, gitlab_token_encrypted = ?
           WHERE id = ?""",
        (body.server, body.token, user["sub"]),
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/users/me/gitlab/status", response_model=GitLabCredentialsStatus)
async def gitlab_credentials_status(user: CurrentUser, db: Db):
    """Check if GitLab credentials are configured."""
    cursor = await db.execute(
        "SELECT gitlab_server, gitlab_token_encrypted FROM users WHERE id = ?",
        (user["sub"],),
    )
    row = await cursor.fetchone()
    if not row:
        return GitLabCredentialsStatus(configured=False)

    configured = bool(row["gitlab_server"] and row["gitlab_token_encrypted"])
    return GitLabCredentialsStatus(
        configured=configured,
        server=row["gitlab_server"] or "",
    )
