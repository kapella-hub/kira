"""Project context module for collaborative development."""

from .analyzer import ProjectAnalyzer, analyze_project
from .manager import ContextManager, get_context_manager
from .models import (
    ChangeEntry,
    ChangeType,
    Convention,
    KnownIssue,
    ProjectContext,
    TechStack,
)

__all__ = [
    # Manager
    "ContextManager",
    "get_context_manager",
    # Analyzer
    "ProjectAnalyzer",
    "analyze_project",
    # Models
    "ProjectContext",
    "ChangeEntry",
    "ChangeType",
    "TechStack",
    "Convention",
    "KnownIssue",
]
