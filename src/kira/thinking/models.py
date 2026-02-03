"""Data models for thinking mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Complexity(Enum):
    """Task complexity levels."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"

    @classmethod
    def from_string(cls, value: str) -> Complexity:
        """Parse complexity from string."""
        value_lower = value.lower().strip().replace(" ", "_").replace("-", "_")
        for complexity in cls:
            if complexity.value == value_lower:
                return complexity
        # Fuzzy matching
        if "very" in value_lower or "high" in value_lower:
            return cls.VERY_COMPLEX
        if "complex" in value_lower or "hard" in value_lower:
            return cls.COMPLEX
        if "moderate" in value_lower or "medium" in value_lower:
            return cls.MODERATE
        if "simple" in value_lower or "easy" in value_lower:
            return cls.SIMPLE
        if "trivial" in value_lower:
            return cls.TRIVIAL
        return cls.MODERATE  # Default


class ThinkingPhase(Enum):
    """Phases of the thinking process."""

    UNDERSTAND = "understand"
    EXPLORE = "explore"
    ANALYZE = "analyze"
    PLAN = "plan"
    CRITIQUE = "critique"
    REFINE = "refine"
    VERIFY = "verify"  # New: validates plan against requirements
    EXECUTE = "execute"


@dataclass
class Approach:
    """A potential approach to solving the task."""

    name: str
    description: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    recommended: bool = False


@dataclass
class TaskUnderstanding:
    """Deep understanding of the task from Phase 1."""

    core_goal: str
    implicit_requirements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class Exploration:
    """Brainstormed approaches from Phase 2."""

    approaches: list[Approach] = field(default_factory=list)
    recommended_approach: str = ""
    reasoning: str = ""
    raw_output: str = ""


@dataclass
class Analysis:
    """Deep analysis from Phase 3."""

    chosen_approach: str
    detailed_reasoning: str
    potential_issues: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class ExecutionStep:
    """A single step in the execution plan."""

    number: int
    action: str
    details: str = ""
    expected_outcome: str = ""
    verification: str = ""


@dataclass
class ExecutionPlan:
    """Detailed execution plan from Phase 4."""

    summary: str
    complexity: Complexity
    steps: list[ExecutionStep] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    estimated_effort: str = "medium"
    raw_output: str = ""

    def to_context(self) -> str:
        """Format plan for display."""
        lines = [
            f"**Summary**: {self.summary}",
            f"**Complexity**: {self.complexity.value}",
            f"**Effort**: {self.estimated_effort}",
        ]

        if self.prerequisites:
            lines.append("")
            lines.append("**Prerequisites**:")
            for prereq in self.prerequisites:
                lines.append(f"  - {prereq}")

        if self.steps:
            lines.append("")
            lines.append("**Execution Steps**:")
            for step in self.steps:
                lines.append(f"  {step.number}. {step.action}")
                if step.details:
                    lines.append(f"     Details: {step.details}")
                if step.expected_outcome:
                    lines.append(f"     Expected: {step.expected_outcome}")

        return "\n".join(lines)


@dataclass
class Critique:
    """Self-critique of the plan from Phase 5."""

    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    blind_spots: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    confidence_score: float = 0.7
    raw_output: str = ""


@dataclass
class RefinedPlan:
    """Refined plan after critique from Phase 6."""

    original_plan: ExecutionPlan | None = None
    refinements_made: list[str] = field(default_factory=list)
    final_steps: list[ExecutionStep] = field(default_factory=list)
    final_summary: str = ""
    confidence_score: float = 0.8
    raw_output: str = ""


@dataclass
class Verification:
    """Verification of plan against requirements from Phase 7."""

    requirements_met: list[str] = field(default_factory=list)
    requirements_missing: list[str] = field(default_factory=list)
    edge_cases_covered: list[str] = field(default_factory=list)
    edge_cases_missing: list[str] = field(default_factory=list)
    ready_to_execute: bool = True
    blocking_issues: list[str] = field(default_factory=list)
    final_confidence: float = 0.8
    raw_output: str = ""

    def to_context(self) -> str:
        """Format refined plan for execution."""
        lines = [f"**Summary**: {self.final_summary}"]

        if self.refinements_made:
            lines.append("")
            lines.append("**Refinements Applied**:")
            for ref in self.refinements_made:
                lines.append(f"  - {ref}")

        if self.final_steps:
            lines.append("")
            lines.append("**Final Execution Steps**:")
            for step in self.final_steps:
                lines.append(f"  {step.number}. {step.action}")
                if step.details:
                    lines.append(f"     {step.details}")
                if step.verification:
                    lines.append(f"     Verify: {step.verification}")

        lines.append("")
        lines.append(f"**Confidence**: {self.confidence_score:.0%}")

        return "\n".join(lines)


@dataclass
class ThinkingResult:
    """Complete result from the thinking process."""

    task: str
    understanding: TaskUnderstanding | None = None
    exploration: Exploration | None = None
    analysis: Analysis | None = None
    initial_plan: ExecutionPlan | None = None
    critique: Critique | None = None
    refined_plan: RefinedPlan | None = None
    verification: Verification | None = None  # New: Phase 7 verification

    # Metadata
    phases_completed: list[ThinkingPhase] = field(default_factory=list)
    total_thinking_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Adaptive reasoning metadata
    was_simplified: bool = False  # True if phases were skipped (trivial task)
    loop_back_count: int = 0  # Number of times we looped back due to low confidence

    def get_final_plan(self) -> str:
        """Get the best available plan for execution."""
        if self.refined_plan and self.refined_plan.final_summary:
            return self.refined_plan.to_context()
        if self.initial_plan:
            return self.initial_plan.to_context()
        return ""

    def to_memory(self) -> str:
        """Format for memory storage (condensed)."""
        parts = [f"Task: {self.task[:100]}"]
        if self.understanding:
            parts.append(f"Goal: {self.understanding.core_goal[:100]}")
        if self.initial_plan:
            parts.append(f"Complexity: {self.initial_plan.complexity.value}")
        if self.refined_plan:
            parts.append(f"Confidence: {self.refined_plan.confidence_score:.0%}")
        return " | ".join(parts)


# Legacy alias for backward compatibility
@dataclass
class ThinkingPlan:
    """Legacy plan format for backward compatibility."""

    task_summary: str
    complexity: Complexity
    steps: list[str] = field(default_factory=list)
    considerations: list[str] = field(default_factory=list)
    estimated_effort: str = "medium"
    raw_output: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_context(self) -> str:
        """Format plan for injection into execution prompt."""
        lines = [
            f"**Summary**: {self.task_summary}",
            f"**Complexity**: {self.complexity.value}",
            f"**Effort**: {self.estimated_effort}",
        ]

        if self.steps:
            lines.append("")
            lines.append("**Steps**:")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"  {i}. {step}")

        if self.considerations:
            lines.append("")
            lines.append("**Considerations**:")
            for consideration in self.considerations:
                lines.append(f"  - {consideration}")

        return "\n".join(lines)

    def to_memory(self) -> str:
        """Format plan for memory storage (condensed)."""
        parts = [f"Task: {self.task_summary}", f"Complexity: {self.complexity.value}"]
        if self.steps:
            parts.append(f"Steps: {'; '.join(self.steps[:3])}")
        return " | ".join(parts)
