"""Git integration module."""

from .assistant import (
    CommitSuggestion,
    GitAssistant,
    GitStatus,
    get_git_assistant,
)

__all__ = [
    "GitAssistant",
    "GitStatus",
    "CommitSuggestion",
    "get_git_assistant",
]
