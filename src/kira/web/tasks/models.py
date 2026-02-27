"""Task Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    task_type: str
    board_id: str
    card_id: str | None
    created_by: str
    assigned_to: str | None
    agent_type: str
    agent_skill: str
    agent_model: str
    prompt_text: str = ""
    payload_json: str = "{}"
    status: str
    priority: int
    source_column_id: str = ""
    target_column_id: str = ""
    failure_column_id: str = ""
    loop_count: int
    max_loop_count: int
    error_summary: str
    created_at: str
    started_at: str | None
    completed_at: str | None


class TaskComplete(BaseModel):
    worker_id: str
    output_text: str = ""
    result_data: dict = {}


class TaskFail(BaseModel):
    worker_id: str
    error_summary: str = ""
    output_text: str = ""


class TaskProgress(BaseModel):
    worker_id: str
    status: str = "running"
    progress_text: str = ""
    step: int | None = None
    total_steps: int | None = None
    phase: str | None = None


class TaskClaim(BaseModel):
    worker_id: str
