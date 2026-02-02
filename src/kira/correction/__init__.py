"""Self-correction system for autonomous execution."""

from .analyzer import FailureAnalyzer
from .loop import SelfCorrector, execute_with_correction
from .models import (
    CorrectionResult,
    CorrectionStrategy,
    ExecutionAttempt,
    FailureAnalysis,
    FailureType,
    RevisionResult,
)
from .reviser import PlanReviser

__all__ = [
    # Core classes
    "SelfCorrector",
    "FailureAnalyzer",
    "PlanReviser",
    # Models
    "ExecutionAttempt",
    "FailureAnalysis",
    "RevisionResult",
    "CorrectionResult",
    "FailureType",
    "CorrectionStrategy",
    # Convenience functions
    "execute_with_correction",
]
