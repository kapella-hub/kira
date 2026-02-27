"""Worker Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class WorkerRegister(BaseModel):
    hostname: str = ""
    worker_version: str = ""
    capabilities: list[str] = ["agent"]


class WorkerResponse(BaseModel):
    worker_id: str
    max_concurrent_tasks: int = 1
    poll_interval_seconds: int = 5
    heartbeat_interval_seconds: int = 30


class WorkerHeartbeat(BaseModel):
    worker_id: str
    running_task_ids: list[str] = []


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    cancel_task_ids: list[str] = []


class WorkerInfo(BaseModel):
    id: str
    user_id: str
    hostname: str
    status: str
    capabilities_json: str
    last_heartbeat: str | None
    registered_at: str
