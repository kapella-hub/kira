"""Data models for self-correction system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FailureType(Enum):
    """Types of execution failures."""

    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TEST_FAILURE = "test_failure"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    LOGIC_ERROR = "logic_error"
    INCOMPLETE = "incomplete"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class CorrectionStrategy(Enum):
    """Strategies for correcting failures."""

    RETRY_SAME = "retry_same"  # Retry with same approach
    MODIFY_APPROACH = "modify_approach"  # Adjust the approach
    ALTERNATIVE_APPROACH = "alternative_approach"  # Try completely different approach
    SIMPLIFY = "simplify"  # Break down into smaller steps
    SEEK_HELP = "seek_help"  # Need human intervention


@dataclass
class ExecutionAttempt:
    """Record of a single execution attempt."""

    attempt_number: int
    action_taken: str
    result: str
    success: bool
    error: str | None = None
    error_type: FailureType | None = None
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_context(self) -> str:
        """Format attempt for injection into prompts."""
        status = "SUCCESS" if self.success else "FAILED"
        lines = [
            f"Attempt #{self.attempt_number} ({status}):",
            f"  Action: {self.action_taken}",
        ]
        if self.error:
            lines.append(f"  Error: {self.error}")
            if self.error_type:
                lines.append(f"  Error Type: {self.error_type.value}")
        if self.result:
            # Truncate long results
            result_preview = self.result[:500] + "..." if len(self.result) > 500 else self.result
            lines.append(f"  Result: {result_preview}")
        return "\n".join(lines)


@dataclass
class FailureAnalysis:
    """Analysis of why an execution failed."""

    failure_type: FailureType
    root_cause: str
    contributing_factors: list[str] = field(default_factory=list)
    suggested_fixes: list[str] = field(default_factory=list)
    recommended_strategy: CorrectionStrategy = CorrectionStrategy.MODIFY_APPROACH
    confidence: float = 0.7
    raw_output: str = ""

    def to_context(self) -> str:
        """Format analysis for injection into prompts."""
        lines = [
            f"Failure Type: {self.failure_type.value}",
            f"Root Cause: {self.root_cause}",
            f"Recommended Strategy: {self.recommended_strategy.value}",
        ]
        if self.contributing_factors:
            lines.append("Contributing Factors:")
            for factor in self.contributing_factors:
                lines.append(f"  - {factor}")
        if self.suggested_fixes:
            lines.append("Suggested Fixes:")
            for fix in self.suggested_fixes:
                lines.append(f"  - {fix}")
        return "\n".join(lines)


@dataclass
class RevisionResult:
    """Result of revising a plan based on failure analysis."""

    original_step: str
    revised_step: str
    revision_reasoning: str
    strategy_used: CorrectionStrategy
    changes_made: list[str] = field(default_factory=list)


@dataclass
class CorrectionResult:
    """Final result of the self-correction loop."""

    success: bool
    final_output: str
    attempts: list[ExecutionAttempt] = field(default_factory=list)
    analyses: list[FailureAnalysis] = field(default_factory=list)
    revisions: list[RevisionResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def attempt_count(self) -> int:
        """Number of attempts made."""
        return len(self.attempts)

    @property
    def was_corrected(self) -> bool:
        """Whether correction was needed to succeed."""
        return self.success and self.attempt_count > 1

    def get_learning_summary(self) -> str:
        """Summarize what was learned for future reference."""
        if not self.analyses:
            return "No corrections needed" if self.success else "Failed without analysis"

        learnings = []
        for analysis in self.analyses:
            learnings.append(f"- {analysis.failure_type.value}: {analysis.root_cause}")
            if analysis.suggested_fixes:
                learnings.append(f"  Fix: {analysis.suggested_fixes[0]}")

        return "\n".join(learnings)
