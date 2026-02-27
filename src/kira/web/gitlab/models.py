"""GitLab task Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class GitLabTestResponse(BaseModel):
    success: bool
    username: str = ""
    error: str = ""


class GitLabProjectInfo(BaseModel):
    id: int
    name: str
    path_with_namespace: str
    web_url: str
    default_branch: str


class GitLabNamespaceInfo(BaseModel):
    id: int
    name: str
    path: str
    kind: str


class LinkProjectRequest(BaseModel):
    board_id: str
    project_id: int
    project_path: str
    project_url: str
    default_branch: str = "main"
    auto_push: bool = True
    push_on_complete: bool = True


class CreateProjectRequest(BaseModel):
    board_id: str
    name: str
    namespace_id: int | None = None
    visibility: str = "private"
    description: str = ""
    auto_push: bool = True
    push_on_complete: bool = True


class GitLabPushRequest(BaseModel):
    branch_name: str = ""
    commit_message: str = ""
    create_mr: bool = True
    mr_title: str = ""


class GitLabTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str = ""
