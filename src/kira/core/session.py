"""SessionManager - Conversation context management.

Bridges our persistent memory with kiro-cli sessions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..context import ContextManager
from ..memory.store import MemoryStore
from ..skills.manager import SkillManager
from .personality import Personality, get_personality


@dataclass
class Session:
    """An active conversation session."""

    id: str
    started_at: datetime
    working_dir: Path
    memory_context: str = ""
    project_context: str = ""  # Shared team context
    active_skills: list[str] = field(default_factory=list)
    skill_prompts: dict[str, str] = field(default_factory=dict)
    personality: Personality | None = None
    inject_personality: bool = True


# Pattern for memory extraction from agent responses
REMEMBER_PATTERN = re.compile(
    r"\[REMEMBER:([^\]]+)\]\s*(.+?)(?=\[REMEMBER:|$)", re.DOTALL
)


class SessionManager:
    """Manages conversation sessions with memory injection.

    Before each kiro-cli invocation, we:
    1. Load relevant memories
    2. Load active skills
    3. Build the context prefix
    """

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        skill_manager: SkillManager | None = None,
    ):
        self.memory = memory_store or MemoryStore()
        self.skills = skill_manager or SkillManager()
        self._current: Session | None = None

    def start(
        self,
        working_dir: Path | None = None,
        skills: list[str] | None = None,
        memory_tags: list[str] | None = None,
        memory_enabled: bool = True,
        max_context_tokens: int = 2000,
        min_importance: int = 3,
        personality: Personality | None = None,
        inject_personality: bool = True,
        context_manager: ContextManager | None = None,
    ) -> Session:
        """Start a new session."""
        session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        work_dir = working_dir or Path.cwd()

        # Load relevant memory context
        memory_context = ""
        if memory_enabled:
            memory_context = self.memory.get_context(
                tags=memory_tags,
                max_tokens=max_context_tokens,
                min_importance=min_importance,
            )

        # Load project context (shared team context)
        project_context = ""
        if context_manager is None:
            context_manager = ContextManager(work_dir)
        if context_manager.exists():
            project_context = context_manager.get_prompt_context()

        # Load skill prompts
        skill_prompts: dict[str, str] = {}
        if skills:
            for skill_name in skills:
                prompt = self.skills.get_prompt(skill_name)
                if prompt:
                    skill_prompts[skill_name] = prompt

        self._current = Session(
            id=session_id,
            started_at=datetime.utcnow(),
            working_dir=work_dir,
            memory_context=memory_context,
            project_context=project_context,
            active_skills=skills or [],
            skill_prompts=skill_prompts,
            personality=personality or get_personality(),
            inject_personality=inject_personality,
        )

        return self._current

    @property
    def current(self) -> Session | None:
        """Get the current session."""
        return self._current

    def build_prompt(self, user_prompt: str, use_brief_personality: bool = False) -> str:
        """Build the full prompt with context.

        Injects personality, project context, memory context and skill prompts
        before the user's prompt.

        Args:
            user_prompt: The user's prompt/task.
            use_brief_personality: Use shorter personality prompt (for context limits).

        Returns:
            Full prompt with all context injected.
        """
        if not self._current:
            return user_prompt

        parts: list[str] = []

        # Add personality prompt first (sets the tone)
        if self._current.inject_personality and self._current.personality:
            if use_brief_personality:
                parts.append(self._current.personality.get_brief_prompt())
            else:
                parts.append(self._current.personality.get_system_prompt())
            parts.append("---")

        # Add project context (shared team knowledge)
        if self._current.project_context:
            parts.append("## Project Context\n\n" + self._current.project_context)
            parts.append("---")

        # Add memory context if available
        if self._current.memory_context:
            parts.append("## Relevant Memory\n\n" + self._current.memory_context)
            parts.append("---")

        # Add skill prompts
        if self._current.skill_prompts:
            for skill_name, prompt in self._current.skill_prompts.items():
                parts.append(f"## Skill: {skill_name}\n\n{prompt}")
            parts.append("---")

        # Add the user prompt
        parts.append("## Task\n\n" + user_prompt)

        return "\n\n".join(parts)

    def extract_memories(self, response: str) -> list[tuple[str, str]]:
        """Extract memories from agent response.

        Looks for explicit memory markers in the output:
        [REMEMBER:key] content to remember
        """
        matches = REMEMBER_PATTERN.findall(response)
        return [(key.strip(), content.strip()) for key, content in matches]

    def save_memories(
        self,
        response: str,
        default_importance: int = 7,
        default_tags: list[str] | None = None,
    ) -> int:
        """Save any memories found in the response.

        Returns the number of memories saved.
        """
        memories = self.extract_memories(response)
        saved = 0

        for key, content in memories:
            # Parse importance from key if provided (e.g., "project:config:8")
            parts = key.rsplit(":", 1)
            importance = default_importance
            if len(parts) == 2 and parts[1].isdigit():
                key = parts[0]
                importance = int(parts[1])

            # Determine tags from key prefix
            tags = list(default_tags or [])
            if ":" in key:
                category = key.split(":")[0]
                if category not in tags:
                    tags.append(category)

            self.memory.store(key, content, tags=tags, importance=importance)
            saved += 1

        return saved

    def add_memory(
        self,
        key: str,
        content: str,
        tags: list[str] | None = None,
        importance: int = 5,
    ) -> None:
        """Manually add a memory."""
        self.memory.store(key, content, tags=tags, importance=importance)

    def search_memories(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list:
        """Search memories."""
        return self.memory.search(query, tags=tags, limit=limit)
