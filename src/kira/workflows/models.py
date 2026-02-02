"""Data models for workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StageStatus(Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class Stage:
    """A single stage in a workflow."""

    name: str
    description: str
    agent: str  # Agent to use for this stage
    prompt_template: str  # Prompt with {placeholders}
    required: bool = True  # Can this stage be skipped?
    depends_on: list[str] = field(default_factory=list)  # Previous stages required
    output_key: str = ""  # Key to store output under

    def __post_init__(self):
        if not self.output_key:
            self.output_key = self.name


@dataclass
class StageResult:
    """Result from a completed stage."""

    stage_name: str
    status: StageStatus
    output: str
    started_at: datetime
    completed_at: datetime
    memories_saved: int = 0

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


@dataclass
class Workflow:
    """A multi-stage workflow definition."""

    name: str
    description: str
    stages: list[Stage]
    triggers: list[str] = field(default_factory=list)  # Keywords that trigger this workflow

    def get_stage(self, name: str) -> Stage | None:
        """Get a stage by name."""
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def get_required_stages(self) -> list[Stage]:
        """Get all required stages."""
        return [s for s in self.stages if s.required]

    def get_optional_stages(self) -> list[Stage]:
        """Get all optional stages."""
        return [s for s in self.stages if not s.required]


@dataclass
class WorkflowExecution:
    """Tracks a workflow execution."""

    workflow_name: str
    original_prompt: str
    started_at: datetime
    stages: dict[str, StageResult] = field(default_factory=dict)
    status: str = "running"  # running, completed, failed, cancelled
    current_stage: str | None = None

    def get_context(self) -> str:
        """Build context from completed stages for injection."""
        parts = []
        for stage_name, result in self.stages.items():
            if result.status == StageStatus.COMPLETED:
                parts.append(f"## {stage_name.title()} Stage Output\n\n{result.output}")
        return "\n\n---\n\n".join(parts)

    def get_outputs(self) -> dict[str, str]:
        """Get outputs from all completed stages."""
        outputs = {"original_prompt": self.original_prompt}
        for stage_name, result in self.stages.items():
            if result.status == StageStatus.COMPLETED:
                outputs[stage_name] = result.output
        return outputs

    @property
    def duration_seconds(self) -> float:
        """Total execution time."""
        if not self.stages:
            return 0.0
        return sum(r.duration_seconds for r in self.stages.values())
