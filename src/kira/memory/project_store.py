"""Project-local memory store - shareable via git.

Stores project-specific knowledge in .kira/project-memory.yaml
which can be committed to the repo for team sharing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import Memory, MemorySource, MemoryType

# Default project memory file
PROJECT_MEMORY_FILE = ".kira/project-memory.yaml"


class ProjectMemoryStore:
    """YAML-backed project memory store.

    Stores memories in a human-readable YAML file that can be:
    - Committed to git
    - Reviewed and edited by developers
    - Merged without conflicts (mostly)

    File format:
    ```yaml
    version: 1
    memories:
      - key: "api-auth-pattern"
        content: "This project uses JWT tokens..."
        tags: ["auth", "api"]
        importance: 7
        memory_type: procedural
        created_at: "2024-01-15T10:30:00"
        created_by: "developer"
    ```
    """

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self.memory_path = self.project_dir / PROJECT_MEMORY_FILE
        self._memories: dict[str, Memory] | None = None

    def exists(self) -> bool:
        """Check if project memory file exists."""
        return self.memory_path.exists()

    def ensure_dir(self) -> None:
        """Ensure .kira directory exists."""
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Memory]:
        """Load memories from YAML file."""
        if self._memories is not None:
            return self._memories

        self._memories = {}

        if not self.memory_path.exists():
            return self._memories

        try:
            content = self.memory_path.read_text()
            data = yaml.safe_load(content) or {}

            for item in data.get("memories", []):
                memory = self._dict_to_memory(item)
                self._memories[memory.key] = memory

        except Exception:
            # If file is corrupted, start fresh
            self._memories = {}

        return self._memories

    def save(self) -> None:
        """Save memories to YAML file."""
        if self._memories is None:
            return

        self.ensure_dir()

        # Sort memories by key for consistent output
        sorted_memories = sorted(self._memories.values(), key=lambda m: m.key)

        data = {
            "version": 1,
            "description": "Project knowledge shared across team. Managed by kira.",
            "memories": [self._memory_to_dict(m) for m in sorted_memories],
        }

        # Write with nice formatting
        content = yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )

        self.memory_path.write_text(content)

    def store(
        self,
        key: str,
        content: str,
        tags: list[str] | None = None,
        importance: int = 5,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        created_by: str | None = None,
    ) -> Memory:
        """Store a project memory."""
        memories = self.load()

        now = datetime.utcnow()

        if key in memories:
            # Update existing
            memory = memories[key]
            memory.content = content
            memory.tags = tags or memory.tags
            memory.importance = importance
            memory.memory_type = memory_type
            memory.updated_at = now
        else:
            # Create new
            memory = Memory(
                key=key,
                content=content,
                tags=tags or [],
                importance=importance,
                memory_type=memory_type,
                source=MemorySource.EXTRACTED,
                created_at=now,
                updated_at=now,
            )
            memories[key] = memory

        self.save()
        return memory

    def get(self, key: str) -> Memory | None:
        """Get a memory by key."""
        return self.load().get(key)

    def delete(self, key: str) -> bool:
        """Delete a memory by key."""
        memories = self.load()
        if key in memories:
            del memories[key]
            self.save()
            return True
        return False

    def list_all(self, tags: list[str] | None = None) -> list[Memory]:
        """List all project memories, optionally filtered by tags."""
        memories = list(self.load().values())

        if tags:
            memories = [m for m in memories if any(t in m.tags for t in tags)]

        return sorted(memories, key=lambda m: -m.importance)

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Simple search by key and content."""
        query_lower = query.lower()
        results = []

        for memory in self.load().values():
            score = 0
            if query_lower in memory.key.lower():
                score += 2
            if query_lower in memory.content.lower():
                score += 1
            if any(query_lower in tag.lower() for tag in memory.tags):
                score += 1

            if score > 0:
                results.append((score, memory))

        # Sort by score, then importance
        results.sort(key=lambda x: (-x[0], -x[1].importance))
        return [m for _, m in results[:limit]]

    def get_context(self, max_tokens: int = 1500, min_importance: int = 3) -> str:
        """Get context string for prompt injection."""
        memories = [m for m in self.load().values() if m.importance >= min_importance]

        # Sort by importance
        memories.sort(key=lambda m: -m.importance)

        lines = []
        char_count = 0
        char_limit = max_tokens * 4  # Rough estimate

        for memory in memories:
            line = memory.to_context()
            if char_count + len(line) > char_limit:
                break
            lines.append(line)
            char_count += len(line)

        if not lines:
            return ""

        return "## Project Knowledge\n\n" + "\n".join(lines)

    def _memory_to_dict(self, memory: Memory) -> dict[str, Any]:
        """Convert Memory to dict for YAML serialization."""
        return {
            "key": memory.key,
            "content": memory.content,
            "tags": memory.tags,
            "importance": memory.importance,
            "memory_type": memory.memory_type.value,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
        }

    def _dict_to_memory(self, data: dict[str, Any]) -> Memory:
        """Convert dict to Memory."""
        # Parse dates
        created_at = datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat()))
        updated_at = datetime.fromisoformat(data.get("updated_at", created_at.isoformat()))

        # Parse memory type
        type_str = data.get("memory_type", "semantic")
        try:
            memory_type = MemoryType(type_str)
        except ValueError:
            memory_type = MemoryType.SEMANTIC

        return Memory(
            key=data["key"],
            content=data["content"],
            tags=data.get("tags", []),
            importance=data.get("importance", 5),
            memory_type=memory_type,
            source=MemorySource.EXTRACTED,
            created_at=created_at,
            updated_at=updated_at,
        )


def get_project_memory(project_dir: Path | None = None) -> ProjectMemoryStore:
    """Get project memory store for given directory."""
    return ProjectMemoryStore(project_dir)
