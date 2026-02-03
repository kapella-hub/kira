"""Memory data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryType(Enum):
    """Types of memories for categorization and retrieval."""

    SEMANTIC = "semantic"  # Facts, definitions, concepts
    EPISODIC = "episodic"  # Conversations, events, decisions
    PROCEDURAL = "procedural"  # How-to, patterns, approaches


class MemorySource(Enum):
    """Source of memory creation."""

    USER = "user"  # Manually added by user
    EXTRACTED = "extracted"  # Auto-extracted from responses
    CONSOLIDATED = "consolidated"  # Merged from multiple memories
    MARKER = "marker"  # Explicit [REMEMBER:] marker


@dataclass
class Memory:
    """A stored memory entry."""

    key: str
    content: str
    tags: list[str] = field(default_factory=list)
    importance: int = 5  # 1-10 scale
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None

    # New fields for enhanced memory system
    memory_type: MemoryType = MemoryType.SEMANTIC
    source: MemorySource = MemorySource.USER
    access_count: int = 0
    last_accessed_at: datetime | None = None

    def to_context(self) -> str:
        """Format for injection into prompts."""
        type_prefix = ""
        if self.memory_type == MemoryType.PROCEDURAL:
            type_prefix = "(how-to) "
        elif self.memory_type == MemoryType.EPISODIC:
            type_prefix = "(event) "
        return f"[{self.key}] {type_prefix}{self.content}"

    def __str__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Memory({self.key}: {content_preview})"

    @property
    def decayed_importance(self) -> float:
        """Calculate importance with time-based decay."""
        if self.last_accessed_at is None:
            reference_time = self.updated_at
        else:
            reference_time = self.last_accessed_at

        days_since = (datetime.utcnow() - reference_time).days
        weeks = days_since / 7

        # 5% decay per week
        decay_rate = 0.95
        decayed = self.importance * (decay_rate**weeks)

        return max(1.0, decayed)


@dataclass
class ExtractedMemory:
    """A memory extracted from LLM response (before storage)."""

    content: str
    memory_type: MemoryType
    confidence: float  # 0.0 - 1.0
    suggested_key: str | None = None
    suggested_importance: int = 5
    suggested_tags: list[str] = field(default_factory=list)
    source_context: str = ""  # Surrounding text for context
