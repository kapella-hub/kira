"""Data models for agent system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TaskType(Enum):
    """Types of tasks that can be classified."""

    CODING = "coding"
    ARCHITECTURE = "architecture"
    DEBUGGING = "debugging"
    DOCUMENTATION = "documentation"
    RESEARCH = "research"
    REVIEW = "review"
    GENERAL = "general"

    @classmethod
    def from_string(cls, value: str) -> TaskType:
        """Parse task type from string."""
        value_lower = value.lower().strip()
        for task_type in cls:
            if task_type.value == value_lower:
                return task_type
        return cls.GENERAL


@dataclass
class ClassifiedTask:
    """Result of task classification."""

    original_prompt: str
    task_type: TaskType
    complexity: str  # simple, moderate, complex
    recommended_agents: list[str]
    confidence: float = 0.0
    reasoning: str = ""

    def is_coding_task(self) -> bool:
        """Check if this is a coding-related task."""
        return self.task_type in (
            TaskType.CODING,
            TaskType.ARCHITECTURE,
            TaskType.DEBUGGING,
        )


@dataclass
class AgentExecution:
    """Tracks a single agent execution."""

    agent_name: str
    started_at: datetime
    prompt: str
    output: str = ""
    status: str = "running"  # running, completed, failed
    duration_seconds: float = 0.0
