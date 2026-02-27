"""Jira task Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class JiraImportRequest(BaseModel):
    jql: str
    board_id: str
    column_id: str


class JiraPushRequest(BaseModel):
    pass


class JiraSyncRequest(BaseModel):
    pass


class JiraTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str = ""
