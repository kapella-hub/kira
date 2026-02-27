"""Board Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class BoardCreate(BaseModel):
    name: str
    description: str = ""


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    settings_json: str | None = None


class BoardResponse(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    settings_json: str
    created_at: str
    updated_at: str


class ColumnResponse(BaseModel):
    id: str
    board_id: str
    name: str
    position: int
    wip_limit: int
    color: str
    collapsed: bool
    agent_type: str = ""
    agent_skill: str = ""
    agent_model: str = "smart"
    auto_run: bool = False
    on_success_column_id: str = ""
    on_failure_column_id: str = ""
    max_loop_count: int = 3
    prompt_template: str = ""


class CardBrief(BaseModel):
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


class FullBoardResponse(BaseModel):
    board: BoardResponse
    columns: list[ColumnWithCards]
    members: list[MemberResponse]


class ColumnWithCards(BaseModel):
    id: str
    board_id: str
    name: str
    position: int
    wip_limit: int
    color: str
    collapsed: bool
    agent_type: str = ""
    agent_skill: str = ""
    agent_model: str = "smart"
    auto_run: bool = False
    on_success_column_id: str = ""
    on_failure_column_id: str = ""
    max_loop_count: int = 3
    prompt_template: str = ""
    cards: list[CardBrief]


class MemberResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    avatar_url: str
    role: str


class ColumnCreate(BaseModel):
    name: str
    color: str = "#6366f1"
    wip_limit: int = 0
    agent_type: str = ""
    agent_skill: str = ""
    agent_model: str = "smart"
    auto_run: bool = False
    on_success_column_id: str = ""
    on_failure_column_id: str = ""
    max_loop_count: int = 3
    prompt_template: str = ""


class ColumnUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    wip_limit: int | None = None
    collapsed: bool | None = None
    agent_type: str | None = None
    agent_skill: str | None = None
    agent_model: str | None = None
    auto_run: bool | None = None
    on_success_column_id: str | None = None
    on_failure_column_id: str | None = None
    max_loop_count: int | None = None
    prompt_template: str | None = None


class ColumnReorder(BaseModel):
    column_ids: list[str]


class GeneratePlanRequest(BaseModel):
    prompt: str


class GenerateCardsRequest(BaseModel):
    prompt: str
    column_id: str = ""  # Target column for new cards; empty = auto-detect first/Plan column


class GeneratePlanResponse(BaseModel):
    board_id: str
    task_id: str


class CreateAndGenerateRequest(BaseModel):
    prompt: str
    name: str = ""


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class UpdateMemberRequest(BaseModel):
    role: str


# Fix forward references
FullBoardResponse.model_rebuild()
