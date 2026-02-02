"""AgentRegistry - Registry of available specialized agents."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentSpec:
    """Specification for a specialized agent."""

    name: str
    description: str
    capabilities: list[str]
    kira: str | None = None  # kiro-cli agent name (if different)
    skill: str | None = None  # Associated skill name
    model_preference: str | None = None  # Preferred model (e.g., "smart", "fast")

    def __str__(self) -> str:
        return f"Agent({self.name}: {self.description})"


# Built-in agent specifications
BUILTIN_AGENTS: dict[str, AgentSpec] = {
    "architect": AgentSpec(
        name="architect",
        description="Designs software architecture and system structure",
        capabilities=["design", "planning", "structure"],
        skill="architect",
        model_preference="smart",
    ),
    "coder": AgentSpec(
        name="coder",
        description="Implements features and writes code",
        capabilities=["coding", "implementation"],
        skill="coder",
        model_preference="smart",
    ),
    "reviewer": AgentSpec(
        name="reviewer",
        description="Reviews code for quality and issues",
        capabilities=["review", "quality"],
        skill="reviewer",
        model_preference="smart",
    ),
    "debugger": AgentSpec(
        name="debugger",
        description="Diagnoses and fixes bugs",
        capabilities=["debugging", "troubleshooting"],
        skill="debugger",
        model_preference="smart",
    ),
    "researcher": AgentSpec(
        name="researcher",
        description="Investigates topics and gathers information",
        capabilities=["research", "analysis"],
        skill="researcher",
        model_preference="smart",
    ),
    "documenter": AgentSpec(
        name="documenter",
        description="Writes documentation and comments",
        capabilities=["documentation"],
        skill="documenter",
        model_preference="smart",
    ),
    "orchestrator": AgentSpec(
        name="orchestrator",
        description="General-purpose agent for any task",
        capabilities=["general"],
        kira="orchestrator",
    ),
}


@dataclass
class AgentRegistry:
    """Registry of available specialized agents."""

    agents: dict[str, AgentSpec] = field(default_factory=lambda: dict(BUILTIN_AGENTS))

    def get(self, name: str) -> AgentSpec | None:
        """Get an agent by name."""
        return self.agents.get(name)

    def list_all(self) -> list[AgentSpec]:
        """List all available agents."""
        return list(self.agents.values())

    def list_for_capabilities(self, capabilities: list[str]) -> list[AgentSpec]:
        """Find agents matching required capabilities."""
        matching = []
        for agent in self.agents.values():
            if any(cap in agent.capabilities for cap in capabilities):
                matching.append(agent)
        return matching

    def register(self, agent: AgentSpec) -> None:
        """Register a new agent."""
        self.agents[agent.name] = agent

    def unregister(self, name: str) -> bool:
        """Unregister an agent."""
        if name in self.agents:
            del self.agents[name]
            return True
        return False
