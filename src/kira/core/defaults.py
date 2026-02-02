"""Default configuration values for Kira.

All configurable defaults are defined here. These can be overridden by:
1. User config file (~/.kira/config.yaml)
2. Project config file (.kira/config.yaml)
3. Environment variables
4. CLI flags

Priority (highest to lowest):
CLI flags > Environment > Project config > User config > Defaults
"""

from __future__ import annotations

# =============================================================================
# CORE SETTINGS
# =============================================================================

# Model to use (None = use kiro-cli default)
DEFAULT_MODEL: str | None = "claude-opus-4.5"

# Trust all tools - enables automatic read/write in working directory
DEFAULT_TRUST_ALL_TOOLS: bool = True

# Command timeout in seconds (20 minutes)
DEFAULT_TIMEOUT: int = 1200

# Default agent type (None = use kiro-cli default)
DEFAULT_AGENT: str | None = None

# Default working directory (None = use current directory)
DEFAULT_WORKING_DIR: str | None = None

# =============================================================================
# MEMORY SYSTEM
# =============================================================================

# Enable memory injection
DEFAULT_MEMORY_ENABLED: bool = True

# Maximum tokens for memory context
DEFAULT_MEMORY_MAX_CONTEXT_TOKENS: int = 2000

# Minimum importance level to include (1-10)
DEFAULT_MEMORY_MIN_IMPORTANCE: int = 3

# Auto-extract memories from agent output
DEFAULT_MEMORY_AUTO_EXTRACT: bool = True

# =============================================================================
# THINKING MODE (--think / -T)
# =============================================================================

# Enable thinking mode by default
DEFAULT_THINKING_ENABLED: bool = True

# Model to use for planning phase (None = same as main model)
DEFAULT_THINKING_PLANNING_MODEL: str | None = None

# Display plan before execution
DEFAULT_THINKING_SHOW_PLAN: bool = True

# Save plans to memory
DEFAULT_THINKING_SAVE_PLANS: bool = True

# =============================================================================
# AUTONOMOUS MODE (--autonomous / -A)
# =============================================================================

# Enable autonomous mode by default
DEFAULT_AUTONOMOUS_ENABLED: bool = False

# Maximum self-correction attempts
DEFAULT_AUTONOMOUS_MAX_RETRIES: int = 3

# Run verification checks after execution
DEFAULT_AUTONOMOUS_VERIFICATION_ENABLED: bool = True

# Run tests as part of verification
DEFAULT_AUTONOMOUS_RUN_TESTS: bool = True

# Run type checking (slower, disabled by default)
DEFAULT_AUTONOMOUS_CHECK_TYPES: bool = False

# Learn from past executions
DEFAULT_AUTONOMOUS_LEARNING_ENABLED: bool = True

# Use LLM for failure analysis
DEFAULT_AUTONOMOUS_DEEP_ANALYSIS: bool = True

# Use 6-phase thinking in autonomous mode
DEFAULT_AUTONOMOUS_DEEP_REASONING: bool = True

# Show detailed progress
DEFAULT_AUTONOMOUS_VERBOSE: bool = False

# =============================================================================
# WORKFLOW SETTINGS
# =============================================================================

# Auto-detect coding tasks
DEFAULT_WORKFLOW_AUTO_DETECT: bool = True

# Confidence threshold for task detection
DEFAULT_WORKFLOW_DETECTION_THRESHOLD: float = 0.6

# Stages to skip by default
DEFAULT_WORKFLOW_SKIP_STAGES: list[str] = []

# Prompt for optional workflow stages
DEFAULT_WORKFLOW_INTERACTIVE: bool = True

# =============================================================================
# PERSONALITY
# =============================================================================

# Enable personality injection
DEFAULT_PERSONALITY_ENABLED: bool = True

# Agent name
DEFAULT_PERSONALITY_NAME: str = "Kira"

# Custom personality instructions (added to base personality)
DEFAULT_PERSONALITY_CUSTOM_INSTRUCTIONS: str = ""

# =============================================================================
# SKILLS
# =============================================================================

# Default skills to load
DEFAULT_SKILLS: list[str] = []


def get_default_config_yaml() -> str:
    """Generate the default configuration as YAML.

    Returns:
        YAML string with all default settings and documentation.
    """
    return '''# Kira-Agent Configuration
# =========================
#
# This file contains all configurable settings for kira.
# Settings can also be overridden by:
#   - Project config: .kira/agent.yaml (overrides this file)
#   - Environment variables: KIRA_*
#   - CLI flags (highest priority)

# -----------------------------------------------------------------------------
# Core Settings
# -----------------------------------------------------------------------------
defaults:
  # Trust all tools - enables automatic read/write in working directory
  trust_all_tools: true

kira:
  # Model to use (fast/smart/opus or full model name)
  model: claude-opus-4.5

  # Command timeout in seconds
  timeout: 1200

  # Default working directory (used when not in a project directory)
  # default_working_dir: ~/Projects

# -----------------------------------------------------------------------------
# Memory System
# -----------------------------------------------------------------------------
memory:
  # Enable memory injection into prompts
  enabled: true

  # Maximum tokens for memory context
  max_context_tokens: 2000

  # Minimum importance level to include (1-10)
  min_importance: 3

  # Auto-extract memories from agent output
  auto_extract: true

# -----------------------------------------------------------------------------
# Thinking Mode (--think / -T)
# Deep 6-phase reasoning: Understand → Explore → Analyze → Plan → Critique → Refine
# -----------------------------------------------------------------------------
thinking:
  # Enable by default (can still toggle with --think flag)
  enabled: true

  # Model for planning phase (leave empty to use main model)
  # Tip: Use a faster model like "fast" for quicker planning
  # planning_model: fast

  # Display plan before execution
  show_plan: true

  # Save plans to memory for future reference
  save_plans: true

# -----------------------------------------------------------------------------
# Autonomous Mode (--autonomous / -A)
# Full autonomous operation with reasoning, self-correction, and verification
# -----------------------------------------------------------------------------
autonomous:
  # Enable by default (can still toggle with --autonomous flag)
  enabled: false

  # Maximum self-correction attempts before giving up
  max_retries: 3

  # Run verification checks after execution
  verification_enabled: true

  # Run tests as part of verification
  run_tests: true

  # Run type checking (mypy/pyright) - slower but catches type issues
  check_types: false

  # Learn from past executions to improve future attempts
  learning_enabled: true

  # Use LLM for deep failure analysis
  deep_analysis: true

  # Use 6-phase thinking in autonomous mode
  deep_reasoning: true

  # Show detailed progress during autonomous execution
  verbose: false

# -----------------------------------------------------------------------------
# Workflow Settings
# Multi-stage workflows for complex tasks (coding, review, etc.)
# -----------------------------------------------------------------------------
workflow:
  # Auto-detect coding tasks and suggest workflows
  auto_detect: true

  # Confidence threshold for task detection (0.0 - 1.0)
  detection_threshold: 0.6

  # Stages to skip by default
  # default_skip_stages:
  #   - docs
  #   - review

  # Prompt for optional workflow stages
  interactive: true

# -----------------------------------------------------------------------------
# Personality
# Kira's personality: witty, professional, optimistic, proactive, creative
# -----------------------------------------------------------------------------
personality:
  # Enable personality injection into prompts
  enabled: true

  # Agent name
  name: Kira

  # Add custom instructions to the personality
  # custom_instructions: |
  #   Always mention relevant documentation links.
  #   Prefer functional programming patterns.

# -----------------------------------------------------------------------------
# Skills
# Default skills to load for every session
# -----------------------------------------------------------------------------
# skills:
#   - architect
#   - coder

# -----------------------------------------------------------------------------
# Deprecated Settings (for backward compatibility)
# -----------------------------------------------------------------------------
# agents:
#   auto_spawn: false
#   use_llm_classification: false
#   default_agent: general
'''


def get_minimal_config_yaml() -> str:
    """Generate a minimal configuration with just the essentials.

    Returns:
        YAML string with minimal settings.
    """
    return '''# Kira-Agent Configuration (Minimal)
# Run `kira config init --full` for all options

defaults:
  trust_all_tools: true

kira:
  model: claude-opus-4.5
  timeout: 1200

memory:
  enabled: true

thinking:
  enabled: true

personality:
  enabled: true
  name: Kira
'''
