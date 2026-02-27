"""Auth Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str = ""


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthConfigResponse(BaseModel):
    auth_mode: str
    demo_users: list[str]


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    preferences: dict | None = None  # Stored as preferences_json


class JiraCredentialsUpdate(BaseModel):
    server: str
    username: str
    token: str


class GitLabCredentialsUpdate(BaseModel):
    server: str
    token: str


class GitLabCredentialsStatus(BaseModel):
    configured: bool
    server: str = ""
