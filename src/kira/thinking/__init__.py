"""Thinking mode - multi-phase reasoning with self-critique."""

from .models import (
    Complexity,
    ThinkingPlan,
    ThinkingPhase,
    ThinkingResult,
    TaskUnderstanding,
    Exploration,
    Analysis,
    ExecutionPlan,
    ExecutionStep,
    Critique,
    RefinedPlan,
    Approach,
    Verification,
)
from .planner import ThinkingPlanner
from .executor import ThinkingExecutor
from .reasoning import DeepReasoning

__all__ = [
    # Models
    "Complexity",
    "ThinkingPlan",
    "ThinkingPhase",
    "ThinkingResult",
    "TaskUnderstanding",
    "Exploration",
    "Analysis",
    "ExecutionPlan",
    "ExecutionStep",
    "Critique",
    "RefinedPlan",
    "Approach",
    "Verification",
    # Legacy (simple two-phase)
    "ThinkingPlanner",
    "ThinkingExecutor",
    # New (deep reasoning)
    "DeepReasoning",
]
