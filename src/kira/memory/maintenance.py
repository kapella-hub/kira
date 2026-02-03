"""Memory maintenance - cleanup, consolidation, and decay management.

Provides tools for:
- Cleaning up old, low-importance memories
- Consolidating duplicate/similar memories
- Managing memory decay over time
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .models import Memory, MemorySource
from .store import MemoryStore


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    deleted_count: int = 0
    deleted_keys: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class ConsolidationResult:
    """Result of a consolidation operation."""

    merged_count: int = 0
    new_memories: list[Memory] = field(default_factory=list)
    deleted_keys: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class DuplicatePair:
    """A pair of similar memories."""

    memory1: Memory
    memory2: Memory
    similarity: float


class MemoryMaintenance:
    """Maintenance operations for the memory store."""

    def __init__(self, store: MemoryStore):
        """Initialize with a memory store.

        Args:
            store: The MemoryStore to maintain.
        """
        self.store = store

    def cleanup(
        self,
        max_age_days: int = 90,
        min_importance: float = 2.0,
        use_decay: bool = True,
        source_filter: MemorySource | None = None,
        dry_run: bool = False,
    ) -> CleanupResult:
        """Clean up old, low-importance memories.

        Args:
            max_age_days: Maximum age in days for low-importance memories.
            min_importance: Minimum importance threshold (after decay if enabled).
            use_decay: Use decayed importance for threshold comparison.
            source_filter: Only clean memories from this source.
            dry_run: If True, don't actually delete, just report what would be deleted.

        Returns:
            CleanupResult with details of the cleanup.
        """
        result = CleanupResult(dry_run=dry_run)

        # Get all memories
        memories = self.store.list_all(source=source_filter, limit=10000)

        now = datetime.utcnow()

        for memory in memories:
            # Calculate age
            age_days = (now - memory.created_at).days

            # Skip if not old enough
            if age_days < max_age_days:
                continue

            # Get effective importance
            if use_decay:
                effective_importance = memory.decayed_importance
            else:
                effective_importance = float(memory.importance)

            # Check if below threshold
            if effective_importance < min_importance:
                result.deleted_keys.append(memory.key)

        result.deleted_count = len(result.deleted_keys)

        # Actually delete if not dry run
        if not dry_run:
            for key in result.deleted_keys:
                self.store.delete(key)

        return result

    def find_duplicates(
        self,
        threshold: float = 0.85,
        limit: int = 100,
    ) -> list[DuplicatePair]:
        """Find near-duplicate memories.

        Args:
            threshold: Similarity threshold (0-1) for considering duplicates.
            limit: Maximum number of pairs to return.

        Returns:
            List of DuplicatePair objects.
        """
        memories = self.store.list_all(limit=1000)
        duplicates: list[DuplicatePair] = []

        # Compare all pairs (O(n^2) but memories should be limited)
        for i, m1 in enumerate(memories):
            for m2 in memories[i + 1 :]:
                similarity = self._calculate_similarity(m1.content, m2.content)

                if similarity >= threshold:
                    duplicates.append(
                        DuplicatePair(
                            memory1=m1,
                            memory2=m2,
                            similarity=similarity,
                        )
                    )

                    if len(duplicates) >= limit:
                        return duplicates

        return duplicates

    def consolidate(
        self,
        threshold: float = 0.85,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        """Merge duplicate memories.

        For each group of similar memories:
        - Keep the one with highest importance
        - Combine tags from all
        - Update content to be most comprehensive
        - Mark as consolidated

        Args:
            threshold: Similarity threshold for merging.
            dry_run: If True, report what would be merged without doing it.

        Returns:
            ConsolidationResult with details.
        """
        result = ConsolidationResult(dry_run=dry_run)

        # Find duplicates
        duplicates = self.find_duplicates(threshold=threshold, limit=100)

        if not duplicates:
            return result

        # Group duplicates (find connected components)
        groups = self._group_duplicates(duplicates)

        for group in groups:
            # Merge the group
            merged = self._merge_group(group)

            if dry_run:
                result.new_memories.append(merged)
                for mem in group:
                    if mem.key != merged.key:
                        result.deleted_keys.append(mem.key)
            else:
                # Store the merged memory
                self.store.store(
                    key=merged.key,
                    content=merged.content,
                    tags=merged.tags,
                    importance=merged.importance,
                    memory_type=merged.memory_type,
                    source=MemorySource.CONSOLIDATED,
                )

                # Delete the others
                for mem in group:
                    if mem.key != merged.key:
                        self.store.delete(mem.key)
                        result.deleted_keys.append(mem.key)

                result.new_memories.append(merged)

        result.merged_count = len(groups)
        return result

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using Jaccard similarity.

        Args:
            text1: First text.
            text2: Second text.

        Returns:
            Similarity score between 0 and 1.
        """
        # Tokenize
        tokens1 = set(self._tokenize(text1))
        tokens2 = set(self._tokenize(text2))

        if not tokens1 or not tokens2:
            return 0.0

        # Jaccard similarity
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into normalized words."""
        # Convert to lowercase and extract words
        words = re.findall(r"\b[a-z]+\b", text.lower())
        # Filter short words
        return [w for w in words if len(w) > 2]

    def _group_duplicates(self, duplicates: list[DuplicatePair]) -> list[list[Memory]]:
        """Group duplicates into connected components."""
        # Build adjacency map
        adjacency: dict[str, set[str]] = {}
        memories_by_key: dict[str, Memory] = {}

        for pair in duplicates:
            key1 = pair.memory1.key
            key2 = pair.memory2.key

            memories_by_key[key1] = pair.memory1
            memories_by_key[key2] = pair.memory2

            if key1 not in adjacency:
                adjacency[key1] = set()
            if key2 not in adjacency:
                adjacency[key2] = set()

            adjacency[key1].add(key2)
            adjacency[key2].add(key1)

        # Find connected components using DFS
        visited: set[str] = set()
        groups: list[list[Memory]] = []

        for start_key in adjacency:
            if start_key in visited:
                continue

            # DFS to find all connected memories
            group_keys: list[str] = []
            stack = [start_key]

            while stack:
                key = stack.pop()
                if key in visited:
                    continue
                visited.add(key)
                group_keys.append(key)

                for neighbor in adjacency.get(key, []):
                    if neighbor not in visited:
                        stack.append(neighbor)

            if len(group_keys) > 1:
                groups.append([memories_by_key[k] for k in group_keys])

        return groups

    def _merge_group(self, memories: list[Memory]) -> Memory:
        """Merge a group of similar memories into one.

        Strategy:
        - Keep the key of the highest importance memory
        - Use the longest content (most comprehensive)
        - Union all tags
        - Take the highest importance
        - Keep the earliest created_at
        """
        if not memories:
            raise ValueError("Cannot merge empty group")

        if len(memories) == 1:
            return memories[0]

        # Sort by importance descending
        sorted_mems = sorted(memories, key=lambda m: m.importance, reverse=True)

        # Find longest content
        longest_content = max(memories, key=lambda m: len(m.content)).content

        # Union tags
        all_tags = set()
        for mem in memories:
            all_tags.update(mem.tags)

        # Earliest created_at
        earliest_created = min(m.created_at for m in memories)

        # Create merged memory
        base = sorted_mems[0]

        return Memory(
            key=base.key,
            content=longest_content,
            tags=list(all_tags),
            importance=base.importance,
            created_at=earliest_created,
            updated_at=datetime.utcnow(),
            memory_type=base.memory_type,
            source=MemorySource.CONSOLIDATED,
            access_count=sum(m.access_count for m in memories),
            last_accessed_at=max(
                (m.last_accessed_at for m in memories if m.last_accessed_at),
                default=None,
            ),
        )

    def get_decay_report(self, limit: int = 50) -> list[dict]:
        """Get a report of memories with their decay status.

        Returns memories sorted by decayed importance, showing
        the difference between original and decayed values.

        Args:
            limit: Maximum number of memories to include.

        Returns:
            List of dicts with memory info and decay details.
        """
        memories = self.store.list_all(limit=limit)

        report = []
        for memory in memories:
            decayed = memory.decayed_importance
            decay_pct = (
                (memory.importance - decayed) / memory.importance * 100
                if memory.importance > 0
                else 0
            )

            report.append(
                {
                    "key": memory.key,
                    "original_importance": memory.importance,
                    "decayed_importance": round(decayed, 2),
                    "decay_percentage": round(decay_pct, 1),
                    "access_count": memory.access_count,
                    "last_accessed": memory.last_accessed_at,
                    "age_days": (datetime.utcnow() - memory.created_at).days,
                }
            )

        # Sort by decay percentage descending
        report.sort(key=lambda x: x["decay_percentage"], reverse=True)
        return report


class MemoryConsolidator:
    """Convenience class for memory consolidation operations."""

    def __init__(self, store: MemoryStore):
        self.maintenance = MemoryMaintenance(store)

    def find_duplicates(self, threshold: float = 0.85) -> list[DuplicatePair]:
        """Find duplicate memory pairs."""
        return self.maintenance.find_duplicates(threshold)

    def merge_duplicates(
        self,
        threshold: float = 0.85,
        dry_run: bool = False,
    ) -> ConsolidationResult:
        """Merge duplicate memories."""
        return self.maintenance.consolidate(threshold, dry_run)
