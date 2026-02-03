"""AgentSpawner - Manages agent lifecycle and execution."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .models import AgentExecution
from .registry import AgentRegistry, AgentSpec

if TYPE_CHECKING:
    from ..core.client import KiraClient
    from ..core.session import SessionManager


@dataclass
class AgentResult:
    """Result from agent execution."""

    agent_name: str
    success: bool
    output: str
    memories_saved: int = 0
    execution_time: float = 0.0


class AgentSpawner:
    """Manages agent lifecycle and execution.

    Spawns specialized agents to handle tasks, tracking their execution
    and results.
    """

    def __init__(
        self,
        kiro_client: KiraClient,
        session_manager: SessionManager,
        registry: AgentRegistry | None = None,
    ):
        self.client = kiro_client
        self.session = session_manager
        self.registry = registry or AgentRegistry()
        self.executions: list[AgentExecution] = []

    async def spawn(
        self,
        agent_name: str,
        prompt: str,
        context: str = "",
    ) -> AsyncIterator[str]:
        """Spawn an agent and stream its output.

        Args:
            agent_name: Name of the agent to spawn
            prompt: The task for the agent
            context: Additional context to inject

        Yields:
            Output chunks from the agent
        """
        agent = self.registry.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")

        execution = AgentExecution(
            agent_name=agent_name,
            started_at=datetime.utcnow(),
            prompt=prompt,
        )
        self.executions.append(execution)

        # Build agent-specific prompt
        full_prompt = self._build_agent_prompt(agent, prompt, context)

        # Create client with agent preferences
        from ..core.client import KiraClient
        from ..core.models import resolve_model

        agent_client = KiraClient(
            agent=agent.kira or self.client.agent,
            model=resolve_model(agent.model_preference) or self.client.model,
            trust_all_tools=self.client.trust_all_tools,
            working_dir=self.client.working_dir,
            timeout=self.client.timeout,
        )

        collected: list[str] = []
        try:
            async for chunk in agent_client.run(full_prompt):
                collected.append(chunk)
                yield chunk

            execution.status = "completed"
            execution.output = "".join(collected)
        except Exception as e:
            execution.status = "failed"
            execution.output = str(e)
            raise
        finally:
            execution.duration_seconds = (datetime.utcnow() - execution.started_at).total_seconds()

    async def spawn_batch(
        self,
        agent_name: str,
        prompt: str,
        context: str = "",
    ) -> AgentResult:
        """Spawn agent and get complete result (non-streaming)."""
        collected: list[str] = []
        async for chunk in self.spawn(agent_name, prompt, context):
            collected.append(chunk)

        output = "".join(collected)

        # Save memories from agent output
        memories_saved = self.session.save_memories(output)

        return AgentResult(
            agent_name=agent_name,
            success=True,
            output=output,
            memories_saved=memories_saved,
            execution_time=self.executions[-1].duration_seconds,
        )

    def _build_agent_prompt(
        self,
        agent: AgentSpec,
        prompt: str,
        context: str = "",
    ) -> str:
        """Build the full prompt for an agent."""
        parts: list[str] = []

        # Add context if provided
        if context:
            parts.append("## Context")
            parts.append("")
            parts.append(context)
            parts.append("")
            parts.append("---")
            parts.append("")

        # Load and add skill prompt if available
        if agent.skill:
            skill_prompt = self.session.skills.get_prompt(agent.skill)
            if skill_prompt:
                parts.append("## Agent Instructions")
                parts.append("")
                parts.append(skill_prompt)
                parts.append("")
                parts.append("---")
                parts.append("")

        # Add the task
        parts.append("## Task")
        parts.append("")
        parts.append(prompt)

        return "\n".join(parts)

    def get_last_execution(self) -> AgentExecution | None:
        """Get the most recent agent execution."""
        return self.executions[-1] if self.executions else None

    def get_execution_history(self) -> list[AgentExecution]:
        """Get all agent executions."""
        return list(self.executions)
