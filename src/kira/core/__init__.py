"""Core module for kira."""

from . import defaults
from .agent import AgentResult, KiraAgent, run_autonomous
from .client import KiraClient, KiraNotFoundError
from .config import (
    AgentConfig,
    AutonomousConfig,
    Config,
    KiraConfig,
    MemoryConfig,
    PersonalityConfig,
    ThinkingConfig,
    WorkflowConfig,
)
from .models import ModelInfo, get_available_models, get_model_info, resolve_model
from .personality import Personality, get_personality
from .verifier import CheckStatus, CheckType, VerificationCheck, VerificationResult, Verifier

__all__ = [
    # Defaults
    "defaults",
    # Agent
    "KiraAgent",
    "AgentResult",
    "run_autonomous",
    # Config
    "Config",
    "KiraConfig",
    "MemoryConfig",
    "ThinkingConfig",
    "WorkflowConfig",
    "AgentConfig",
    "AutonomousConfig",
    "PersonalityConfig",
    # Personality
    "Personality",
    "get_personality",
    # Kira client
    "KiraClient",
    "KiraNotFoundError",
    # Models
    "ModelInfo",
    "get_available_models",
    "get_model_info",
    "resolve_model",
    # Verifier
    "Verifier",
    "VerificationResult",
    "VerificationCheck",
    "CheckType",
    "CheckStatus",
]
