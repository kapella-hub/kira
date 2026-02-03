"""Kira-Agent: Autonomous CLI agent with deep reasoning and self-correction.

Kira-Agent is an agentic CLI wrapper for kiro-cli that provides:
- Deep 6-phase reasoning for complex task analysis
- Self-correction loop with automatic error recovery
- Verification layer for validating results
- Execution memory for learning from past attempts
- Persistent memory and skills system

Usage:
    # CLI (interactive)
    $ kira

    # CLI (one-shot)
    $ kira chat "implement user authentication"

    # CLI (autonomous mode)
    $ kira chat -A "build a REST API"

    # Python API
    from kira import KiraAgent

    agent = KiraAgent()
    result = await agent.run("implement user authentication")
"""

try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("kira")
except Exception:
    __version__ = "0.0.0-dev"


# Core exports (lazy imports for faster startup)
def __getattr__(name: str):
    """Lazy import for main classes."""
    if name == "KiraAgent":
        from .core.agent import KiraAgent

        return KiraAgent
    if name == "AgentResult":
        from .core.agent import AgentResult

        return AgentResult
    if name == "Config":
        from .core.config import Config

        return Config
    if name == "KiraClient":
        from .core.client import KiraClient

        return KiraClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "KiraAgent",
    "AgentResult",
    "Config",
    "KiraClient",
]
