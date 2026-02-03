"""SessionManager - Conversation context management.

Bridges our persistent memory with kiro-cli sessions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..context import ContextManager
from ..context.smart import SmartContextLoader
from ..memory.extractor import MemoryExtractor
from ..memory.failures import FailureLearning
from ..memory.models import MemorySource, MemoryType
from ..memory.project_store import ProjectMemoryStore
from ..memory.store import MemoryStore
from ..rules import RulesManager
from ..skills.manager import SkillManager
from .personality import Personality, get_personality


@dataclass
class Session:
    """An active conversation session."""

    id: str
    started_at: datetime
    working_dir: Path
    memory_context: str = ""
    project_context: str = ""  # Shared team context from .kira/context.md
    project_memory_context: str = ""  # Shared team memory from .kira/project-memory.yaml
    active_skills: list[str] = field(default_factory=list)
    skill_prompts: dict[str, str] = field(default_factory=dict)
    personality: Personality | None = None
    inject_personality: bool = True
    smart_context_enabled: bool = True  # Auto-load relevant files
    rules_enabled: bool = True  # Auto-inject coding rules based on task
    # Conversation tracking for better memory
    turn_count: int = 0
    conversation_topics: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)


# Pattern for memory extraction from agent responses
REMEMBER_PATTERN = re.compile(r"\[REMEMBER:([^\]]+)\]\s*(.+?)(?=\[REMEMBER:|$)", re.DOTALL)

# Pattern for project memory (shared with team)
PROJECT_PATTERN = re.compile(r"\[PROJECT:([^\]]+)\]\s*(.+?)(?=\[PROJECT:|$)", re.DOTALL)


class SessionManager:
    """Manages conversation sessions with memory injection.

    Before each kiro-cli invocation, we:
    1. Load relevant memories (user-local and project-local)
    2. Load active skills
    3. Load coding rules
    4. Build the context prefix
    """

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        skill_manager: SkillManager | None = None,
        project_memory: ProjectMemoryStore | None = None,
        failure_learning: FailureLearning | None = None,
        rules_manager: RulesManager | None = None,
    ):
        self.memory = memory_store or MemoryStore()
        self.skills = skill_manager or SkillManager()
        self.project_memory = project_memory  # Set per-session based on working dir
        self.failure_learning = failure_learning or FailureLearning()
        self.rules = rules_manager  # Set per-session based on working dir
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
        rules_enabled: bool = True,
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

        # Load project context (shared team context from .kira/context.md)
        project_context = ""
        if context_manager is None:
            context_manager = ContextManager(work_dir)
        if context_manager.exists():
            project_context = context_manager.get_prompt_context()

        # Load project memory (shared team knowledge from .kira/project-memory.yaml)
        project_memory_context = ""
        self.project_memory = ProjectMemoryStore(work_dir)
        if self.project_memory.exists():
            project_memory_context = self.project_memory.get_context(
                max_tokens=max_context_tokens // 2,  # Share budget with user memory
                min_importance=min_importance,
            )

        # Initialize rules manager for this working directory
        self.rules = RulesManager(work_dir)
        if rules_enabled:
            self.rules.load()  # Pre-load rules at session start

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
            project_memory_context=project_memory_context,
            active_skills=skills or [],
            skill_prompts=skill_prompts,
            personality=personality or get_personality(),
            inject_personality=inject_personality,
            rules_enabled=rules_enabled,
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

        # Add project context (shared team knowledge from .kira/context.md)
        if self._current.project_context:
            parts.append("## Project Context\n\n" + self._current.project_context)
            parts.append("---")

        # Add project memory (shared team knowledge from .kira/project-memory.yaml)
        if self._current.project_memory_context:
            parts.append(self._current.project_memory_context)
            parts.append("---")

        # Add user memory context if available
        if self._current.memory_context:
            parts.append("## Your Memory\n\n" + self._current.memory_context)
            parts.append("---")

        # Add skill prompts
        if self._current.skill_prompts:
            for skill_name, prompt in self._current.skill_prompts.items():
                parts.append(f"## Skill: {skill_name}\n\n{prompt}")
            parts.append("---")

        # Add rules context (auto-detected based on task type)
        if self._current.rules_enabled:
            rules_context = self._load_rules_context(user_prompt)
            if rules_context:
                parts.append(rules_context)
                parts.append("---")

        # Add smart context (auto-detected relevant files)
        if self._current.smart_context_enabled:
            smart_context = self._load_smart_context(user_prompt)
            if smart_context:
                parts.append(smart_context)
                parts.append("---")

        # Add failure warnings (learn from past mistakes)
        failure_warnings = self._load_failure_warnings(user_prompt)
        if failure_warnings:
            parts.append(failure_warnings)
            parts.append("---")

        # Add the user prompt
        parts.append("## Task\n\n" + user_prompt)

        return "\n\n".join(parts)

    def _load_smart_context(self, prompt: str) -> str:
        """Load smart context based on the prompt."""
        if not self._current:
            return ""

        try:
            loader = SmartContextLoader(self._current.working_dir)
            context = loader.load(prompt, max_files=5)
            return context.get_context_string(max_chars=3000)
        except Exception:
            return ""

    def _load_rules_context(self, prompt: str) -> str:
        """Load rules context based on the task type."""
        if not self.rules:
            return ""

        try:
            return self.rules.get_context(prompt, max_rulesets=2)
        except Exception:
            return ""

    def _load_failure_warnings(self, prompt: str) -> str:
        """Load relevant failure warnings."""
        try:
            return self.failure_learning.get_context_string(prompt, max_warnings=3)
        except Exception:
            return ""

    def record_failure(
        self,
        error_type: str,
        error_message: str,
        context: str,
        solution: str = "",
        task: str = "",
    ) -> None:
        """Record a failure for future learning."""
        try:
            self.failure_learning.record_failure(
                error_type=error_type,
                error_message=error_message,
                context=context,
                solution=solution,
                task=task,
            )
        except Exception:
            pass  # Don't fail on learning errors

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
        prompt: str = "",
        default_importance: int = 7,
        default_tags: list[str] | None = None,
        auto_extract: bool = True,
    ) -> int:
        """Save memories from the response.

        Uses both explicit markers and auto-extraction.

        Returns the number of memories saved.
        """
        saved = 0

        # 1. Extract explicit [REMEMBER:key] markers
        explicit_memories = self.extract_memories(response)

        for key, content in explicit_memories:
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

            self.memory.store(
                key,
                content,
                tags=tags,
                importance=importance,
                source=MemorySource.EXTRACTED,
            )
            saved += 1

        # 2. Auto-extract using pattern matching
        if auto_extract:
            extractor = MemoryExtractor(min_confidence=0.7)
            result = extractor.extract(response, task=prompt)

            for extracted in result.extracted:
                # Don't duplicate explicit memories
                if any(extracted.content in content for _, content in explicit_memories):
                    continue

                self.memory.store(
                    extracted.suggested_key,
                    extracted.content,
                    tags=extracted.suggested_tags,
                    importance=extracted.suggested_importance,
                    memory_type=extracted.memory_type,
                    source=MemorySource.EXTRACTED,
                )
                saved += 1

        # 3. Track conversation turn
        if self._current:
            self._current.turn_count += 1

        return saved

    def refresh_memory_context(
        self,
        query: str = "",
        max_tokens: int = 2000,
        min_importance: int = 3,
    ) -> str:
        """Refresh memory context based on current conversation.

        Call this to get updated memories relevant to the current topic.
        """
        if not self._current:
            return ""

        # If we have a query, search for relevant memories
        if query:
            memories = self.memory.search(query, limit=10)
            if memories:
                context_parts = [m.to_context() for m in memories]
                return "## Relevant Memory\n\n" + "\n".join(context_parts)

        # Otherwise return general context
        return self.memory.get_context(
            max_tokens=max_tokens,
            min_importance=min_importance,
        )

    def save_conversation_summary(self, summary: str) -> None:
        """Save a summary of the conversation as episodic memory."""
        if not self._current:
            return

        key = f"session:{self._current.id}"
        self.memory.store(
            key=key,
            content=summary,
            tags=["session", "conversation"],
            importance=6,
            memory_type=MemoryType.EPISODIC,
            source=MemorySource.EXTRACTED,
        )

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

    def extract_project_memories(self, response: str) -> list[tuple[str, str]]:
        """Extract project memories from agent response.

        Looks for explicit project memory markers:
        [PROJECT:key] content to share with team
        """
        matches = PROJECT_PATTERN.findall(response)
        return [(key.strip(), content.strip()) for key, content in matches]

    def save_project_memory(
        self,
        key: str,
        content: str,
        tags: list[str] | None = None,
        importance: int = 6,
        memory_type: MemoryType = MemoryType.SEMANTIC,
    ) -> bool:
        """Save a memory to project store (shared with team).

        These memories are stored in .kira/project-memory.yaml
        and can be committed to git.
        """
        if not self.project_memory:
            return False

        self.project_memory.store(
            key=key,
            content=content,
            tags=tags or [],
            importance=importance,
            memory_type=memory_type,
        )
        return True

    def save_all_memories(
        self,
        response: str,
        prompt: str = "",
        default_importance: int = 7,
        default_tags: list[str] | None = None,
        auto_extract: bool = True,
    ) -> tuple[int, int]:
        """Save both user and project memories from response.

        Returns (user_memories_saved, project_memories_saved).
        """
        user_saved = self.save_memories(
            response, prompt, default_importance, default_tags, auto_extract
        )

        # Extract and save project memories
        project_saved = 0
        project_memories = self.extract_project_memories(response)

        for key, content in project_memories:
            # Parse importance from key if provided
            parts = key.rsplit(":", 1)
            importance = 6
            if len(parts) == 2 and parts[1].isdigit():
                key = parts[0]
                importance = int(parts[1])

            # Determine tags from key prefix
            tags = list(default_tags or [])
            if ":" in key:
                category = key.split(":")[0]
                if category not in tags:
                    tags.append(category)

            if self.save_project_memory(key, content, tags=tags, importance=importance):
                project_saved += 1

        return user_saved, project_saved
