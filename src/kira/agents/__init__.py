"""Agent system - task classification and specialized agent spawning.

.. deprecated::
    The multi-agent system is deprecated in favor of the unified KiraAgent.
    Use `from kira.core import KiraAgent` instead.

    The unified agent provides:
    - Deep 6-phase reasoning
    - Self-correction loop with automatic error recovery
    - Verification layer for validating results
    - Execution memory for learning from past attempts

    Example migration::

        # Old (deprecated):
        from kira.agents import TaskClassifier, AgentSpawner
        classifier = TaskClassifier(client)
        classified = await classifier.classify(prompt)
        spawner = AgentSpawner(client, session, registry)
        result = await spawner.spawn(classified.task_type.value, prompt)

        # New (recommended):
        from kira.core import KiraAgent
        agent = KiraAgent()
        result = await agent.run(prompt)
"""

import warnings

from .classifier import TaskClassifier
from .models import ClassifiedTask, TaskType
from .registry import AgentRegistry, AgentSpec
from .spawner import AgentResult, AgentSpawner

__all__ = [
    "TaskType",
    "ClassifiedTask",
    "TaskClassifier",
    "AgentSpec",
    "AgentRegistry",
    "AgentSpawner",
    "AgentResult",
]

# Issue deprecation warning on import
warnings.warn(
    "The kira.agents module is deprecated. "
    "Use kira.core.KiraAgent for autonomous operation instead.",
    DeprecationWarning,
    stacklevel=2,
)
