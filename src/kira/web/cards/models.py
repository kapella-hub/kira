"""Card Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class CardCreate(BaseModel):
    column_id: str
    title: str
    description: str = ""
    assignee_id: str | None = None
    priority: str = "medium"
    labels: str = "[]"
    due_date: str | None = None


class CardUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_id: str | None = None
    priority: str | None = None
    labels: str | None = None
    due_date: str | None = None
    agent_status: str | None = None


class CardMove(BaseModel):
    column_id: str
    position: int


class CardReorder(BaseModel):
    column_id: str
    card_ids: list[str]


class CardResponse(BaseModel):
    id: str
    column_id: str
    board_id: str
    title: str
    description: str
    position: int
    assignee_id: str | None
    priority: str
    labels: str
    due_date: str | None
    jira_key: str
    jira_sync_status: str
    agent_status: str
    created_by: str | None
    created_at: str
    updated_at: str


class CommentCreate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: str
    card_id: str
    user_id: str
    content: str
    is_agent_output: bool
    created_at: str
