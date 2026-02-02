"""Relevance scoring for memory retrieval.

Scores memories against the current task using multiple factors:
- Keyword overlap (TF-IDF style)
- Recency boost
- Access frequency
- Memory type matching
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime

from .models import Memory, MemoryType


# Stop words to ignore in keyword matching
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "i", "you", "he", "she", "it", "we",
    "they", "what", "which", "who", "whom", "how", "when", "where", "why",
}

# Keywords that suggest procedural memory
PROCEDURAL_KEYWORDS = {
    "how", "implement", "create", "build", "setup", "configure", "install",
    "deploy", "run", "execute", "fix", "solve", "handle", "process",
    "step", "guide", "tutorial", "pattern", "approach", "method",
}

# Keywords that suggest episodic memory
EPISODIC_KEYWORDS = {
    "decided", "chose", "discussed", "agreed", "meeting", "conversation",
    "yesterday", "today", "last", "previous", "history", "event", "happened",
}


class RelevanceScorer:
    """Scores memories for relevance to a given task."""

    def __init__(
        self,
        keyword_weight: float = 0.4,
        recency_weight: float = 0.2,
        frequency_weight: float = 0.2,
        type_weight: float = 0.2,
    ):
        """Initialize scorer with configurable weights.

        Args:
            keyword_weight: Weight for keyword overlap score (0-1).
            recency_weight: Weight for recency score (0-1).
            frequency_weight: Weight for access frequency score (0-1).
            type_weight: Weight for memory type match score (0-1).
        """
        self.keyword_weight = keyword_weight
        self.recency_weight = recency_weight
        self.frequency_weight = frequency_weight
        self.type_weight = type_weight

    def score(self, memory: Memory, task: str) -> float:
        """Calculate relevance score for a memory.

        Args:
            memory: The memory to score.
            task: The current task/query.

        Returns:
            Relevance score between 0.0 and 1.0.
        """
        keyword_score = self._keyword_overlap(memory, task)
        recency_score = self._recency_factor(memory)
        frequency_score = self._frequency_factor(memory)
        type_score = self._type_match(memory, task)

        total = (
            keyword_score * self.keyword_weight +
            recency_score * self.recency_weight +
            frequency_score * self.frequency_weight +
            type_score * self.type_weight
        )

        return min(1.0, max(0.0, total))

    def score_batch(
        self,
        memories: list[Memory],
        task: str,
        min_score: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """Score multiple memories and filter by minimum score.

        Args:
            memories: List of memories to score.
            task: The current task/query.
            min_score: Minimum score threshold.

        Returns:
            List of (memory, score) tuples, sorted by score descending.
        """
        scored = []
        for memory in memories:
            score = self.score(memory, task)
            if score >= min_score:
                scored.append((memory, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words, removing stop words."""
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-z]+\b', text.lower())
        # Remove stop words and short words
        return [w for w in words if w not in STOP_WORDS and len(w) > 2]

    def _keyword_overlap(self, memory: Memory, task: str) -> float:
        """Calculate keyword overlap using TF-IDF style scoring."""
        task_tokens = self._tokenize(task)
        memory_tokens = self._tokenize(memory.content + " " + memory.key)

        if not task_tokens or not memory_tokens:
            return 0.0

        task_counts = Counter(task_tokens)
        memory_counts = Counter(memory_tokens)

        # Calculate overlap
        overlap = 0
        for token, count in task_counts.items():
            if token in memory_counts:
                # TF-IDF style: log(1 + count) for both
                overlap += math.log(1 + count) * math.log(1 + memory_counts[token])

        # Normalize by task length
        max_possible = sum(math.log(1 + c) ** 2 for c in task_counts.values())
        if max_possible == 0:
            return 0.0

        return min(1.0, overlap / max_possible)

    def _recency_factor(self, memory: Memory) -> float:
        """Calculate recency score with exponential decay."""
        reference_time = memory.last_accessed_at or memory.updated_at
        days_ago = (datetime.utcnow() - reference_time).days

        # Exponential decay: score = 0.95^(days/7)
        # Recent memories (< 1 week) score ~1.0
        # 1 month old: ~0.8
        # 3 months old: ~0.5
        decay_rate = 0.95
        weeks = days_ago / 7

        return decay_rate ** weeks

    def _frequency_factor(self, memory: Memory) -> float:
        """Calculate frequency score based on access count."""
        # Logarithmic scaling: log(1 + access_count) / log(1 + max_expected)
        # Assumes typical max of ~100 accesses
        max_expected = 100
        score = math.log(1 + memory.access_count) / math.log(1 + max_expected)
        return min(1.0, score)

    def _type_match(self, memory: Memory, task: str) -> float:
        """Score based on memory type appropriateness for the task."""
        task_lower = task.lower()
        task_tokens = set(self._tokenize(task))

        # Detect task type
        is_procedural_task = bool(task_tokens & PROCEDURAL_KEYWORDS)
        is_episodic_task = bool(task_tokens & EPISODIC_KEYWORDS)

        # Score based on match
        if memory.memory_type == MemoryType.PROCEDURAL:
            if is_procedural_task:
                return 1.0
            elif is_episodic_task:
                return 0.3
            else:
                return 0.6

        elif memory.memory_type == MemoryType.EPISODIC:
            if is_episodic_task:
                return 1.0
            elif is_procedural_task:
                return 0.3
            else:
                return 0.5

        else:  # SEMANTIC
            # Semantic memories are generally useful
            if is_procedural_task or is_episodic_task:
                return 0.5
            else:
                return 0.8

    def suggest_type(self, task: str) -> MemoryType | None:
        """Suggest the most appropriate memory type for a task.

        Args:
            task: The task description.

        Returns:
            Suggested MemoryType, or None if no strong preference.
        """
        task_tokens = set(self._tokenize(task))

        procedural_matches = len(task_tokens & PROCEDURAL_KEYWORDS)
        episodic_matches = len(task_tokens & EPISODIC_KEYWORDS)

        if procedural_matches > episodic_matches and procedural_matches >= 2:
            return MemoryType.PROCEDURAL
        elif episodic_matches > procedural_matches and episodic_matches >= 2:
            return MemoryType.EPISODIC
        else:
            return None


def get_relevant_memories(
    memories: list[Memory],
    task: str,
    max_count: int = 10,
    min_relevance: float = 0.3,
    scorer: RelevanceScorer | None = None,
) -> list[Memory]:
    """Get the most relevant memories for a task.

    Convenience function that creates a scorer and returns filtered memories.

    Args:
        memories: List of memories to filter.
        task: The current task/query.
        max_count: Maximum number of memories to return.
        min_relevance: Minimum relevance score threshold.
        scorer: Optional pre-configured scorer.

    Returns:
        List of relevant memories, sorted by relevance.
    """
    if not scorer:
        scorer = RelevanceScorer()

    scored = scorer.score_batch(memories, task, min_score=min_relevance)
    return [memory for memory, _ in scored[:max_count]]
