"""Configuration management for kira."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import defaults as D


@dataclass
class KiraConfig:
    """Configuration for kiro-cli invocation."""

    agent: str | None = None
    model: str | None = D.DEFAULT_MODEL
    trust_all_tools: bool = D.DEFAULT_TRUST_ALL_TOOLS
    working_dir: Path | None = None
    default_working_dir: str | None = D.DEFAULT_WORKING_DIR
    timeout: int = D.DEFAULT_TIMEOUT


@dataclass
class MemoryConfig:
    """Memory system configuration."""

    enabled: bool = D.DEFAULT_MEMORY_ENABLED
    max_context_tokens: int = D.DEFAULT_MEMORY_MAX_CONTEXT_TOKENS
    min_importance: int = D.DEFAULT_MEMORY_MIN_IMPORTANCE
    auto_extract: bool = D.DEFAULT_MEMORY_AUTO_EXTRACT
    db_path: Path | None = None


@dataclass
class ThinkingConfig:
    """Thinking mode configuration."""

    enabled: bool = D.DEFAULT_THINKING_ENABLED
    planning_model: str | None = D.DEFAULT_THINKING_PLANNING_MODEL
    show_plan: bool = D.DEFAULT_THINKING_SHOW_PLAN
    save_plans: bool = D.DEFAULT_THINKING_SAVE_PLANS


@dataclass
class WorkflowConfig:
    """Workflow orchestration configuration."""

    auto_detect: bool = D.DEFAULT_WORKFLOW_AUTO_DETECT
    detection_threshold: float = D.DEFAULT_WORKFLOW_DETECTION_THRESHOLD
    default_skip_stages: list[str] = field(
        default_factory=lambda: D.DEFAULT_WORKFLOW_SKIP_STAGES.copy()
    )
    interactive: bool = D.DEFAULT_WORKFLOW_INTERACTIVE


@dataclass
class AgentConfig:
    """Agent spawning configuration (deprecated - use AutonomousConfig)."""

    auto_spawn: bool = False
    use_llm_classification: bool = False
    default_agent: str = "general"


@dataclass
class AutonomousConfig:
    """Configuration for autonomous agent operation."""

    enabled: bool = D.DEFAULT_AUTONOMOUS_ENABLED
    max_retries: int = D.DEFAULT_AUTONOMOUS_MAX_RETRIES
    verification_enabled: bool = D.DEFAULT_AUTONOMOUS_VERIFICATION_ENABLED
    run_tests: bool = D.DEFAULT_AUTONOMOUS_RUN_TESTS
    check_types: bool = D.DEFAULT_AUTONOMOUS_CHECK_TYPES
    learning_enabled: bool = D.DEFAULT_AUTONOMOUS_LEARNING_ENABLED
    deep_analysis: bool = D.DEFAULT_AUTONOMOUS_DEEP_ANALYSIS
    deep_reasoning: bool = D.DEFAULT_AUTONOMOUS_DEEP_REASONING
    verbose: bool = D.DEFAULT_AUTONOMOUS_VERBOSE


@dataclass
class PersonalityConfig:
    """Agent personality configuration."""

    enabled: bool = D.DEFAULT_PERSONALITY_ENABLED
    name: str = D.DEFAULT_PERSONALITY_NAME
    custom_instructions: str = D.DEFAULT_PERSONALITY_CUSTOM_INSTRUCTIONS


@dataclass
class Config:
    """Main application configuration."""

    kira: KiraConfig = field(default_factory=KiraConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    thinking: ThinkingConfig = field(default_factory=ThinkingConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    autonomous: AutonomousConfig = field(default_factory=AutonomousConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    default_agent: str | None = D.DEFAULT_AGENT
    default_skills: list[str] = field(default_factory=lambda: D.DEFAULT_SKILLS.copy())

    # Standard paths
    USER_CONFIG_DIR: Path = Path.home() / ".kira"
    USER_DATA_DIR: Path = Path.home() / ".kira" / "data"
    USER_CONFIG_FILE: Path = USER_CONFIG_DIR / "config.yaml"
    PROJECT_CONFIG_FILE: Path = Path(".kira") / "config.yaml"

    @classmethod
    def load(cls, project_dir: Path | None = None) -> Config:
        """Load configuration from user and project files."""
        config = cls()

        # Load user config
        if cls.USER_CONFIG_FILE.exists():
            config._merge_from_file(cls.USER_CONFIG_FILE)

        # Load project config (overrides user)
        project_config = (project_dir or Path.cwd()) / ".kira" / "config.yaml"
        if project_config.exists():
            config._merge_from_file(project_config)

        # Environment overrides
        config._apply_env_overrides()

        return config

    def _merge_from_file(self, path: Path) -> None:
        """Merge configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Apply defaults section
        defaults = data.get("defaults", {})
        if "agent" in defaults:
            self.default_agent = defaults["agent"]
        if "trust_all_tools" in defaults:
            self.kira.trust_all_tools = defaults["trust_all_tools"]

        # Apply kira section
        kira_section = data.get("kira", {})
        if "model" in kira_section:
            self.kira.model = kira_section["model"]
        if "timeout" in kira_section:
            self.kira.timeout = kira_section["timeout"]
        if "default_working_dir" in kira_section:
            self.kira.default_working_dir = kira_section["default_working_dir"]

        # Apply memory section
        memory = data.get("memory", {})
        if "enabled" in memory:
            self.memory.enabled = memory["enabled"]
        if "max_context_tokens" in memory:
            self.memory.max_context_tokens = memory["max_context_tokens"]
        if "min_importance" in memory:
            self.memory.min_importance = memory["min_importance"]
        if "auto_extract" in memory:
            self.memory.auto_extract = memory["auto_extract"]

        # Apply skills
        if "skills" in data:
            self.default_skills = data["skills"]

        # Apply thinking section
        thinking = data.get("thinking", {})
        if "enabled" in thinking:
            self.thinking.enabled = thinking["enabled"]
        if "planning_model" in thinking:
            self.thinking.planning_model = thinking["planning_model"]
        if "show_plan" in thinking:
            self.thinking.show_plan = thinking["show_plan"]
        if "save_plans" in thinking:
            self.thinking.save_plans = thinking["save_plans"]

        # Apply workflow section
        workflow = data.get("workflow", {})
        if "auto_detect" in workflow:
            self.workflow.auto_detect = workflow["auto_detect"]
        if "detection_threshold" in workflow:
            self.workflow.detection_threshold = workflow["detection_threshold"]
        if "default_skip_stages" in workflow:
            self.workflow.default_skip_stages = workflow["default_skip_stages"]
        if "interactive" in workflow:
            self.workflow.interactive = workflow["interactive"]

        # Apply agents section
        agents = data.get("agents", {})
        if "auto_spawn" in agents:
            self.agents.auto_spawn = agents["auto_spawn"]
        if "use_llm_classification" in agents:
            self.agents.use_llm_classification = agents["use_llm_classification"]
        if "default_agent" in agents:
            self.agents.default_agent = agents["default_agent"]

        # Apply autonomous section
        autonomous = data.get("autonomous", {})
        if "enabled" in autonomous:
            self.autonomous.enabled = autonomous["enabled"]
        if "max_retries" in autonomous:
            self.autonomous.max_retries = autonomous["max_retries"]
        if "verification_enabled" in autonomous:
            self.autonomous.verification_enabled = autonomous["verification_enabled"]
        if "run_tests" in autonomous:
            self.autonomous.run_tests = autonomous["run_tests"]
        if "check_types" in autonomous:
            self.autonomous.check_types = autonomous["check_types"]
        if "learning_enabled" in autonomous:
            self.autonomous.learning_enabled = autonomous["learning_enabled"]
        if "deep_analysis" in autonomous:
            self.autonomous.deep_analysis = autonomous["deep_analysis"]
        if "deep_reasoning" in autonomous:
            self.autonomous.deep_reasoning = autonomous["deep_reasoning"]
        if "verbose" in autonomous:
            self.autonomous.verbose = autonomous["verbose"]

        # Apply personality section
        personality = data.get("personality", {})
        if "enabled" in personality:
            self.personality.enabled = personality["enabled"]
        if "name" in personality:
            self.personality.name = personality["name"]
        if "custom_instructions" in personality:
            self.personality.custom_instructions = personality["custom_instructions"]

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides."""
        if model := os.environ.get("KIRA_MODEL"):
            self.kira.model = model
        if agent := os.environ.get("KIRA_DEFAULT_AGENT"):
            self.default_agent = agent
        if os.environ.get("KIRA_TRUST_ALL", "").lower() in ("1", "true", "yes"):
            self.kira.trust_all_tools = True

    def save_user_config(self) -> None:
        """Save current configuration to user config file."""
        self.USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "defaults": {
                "agent": self.default_agent,
                "trust_all_tools": self.kira.trust_all_tools,
            },
            "kira": {
                "timeout": self.kira.timeout,
            },
            "memory": {
                "enabled": self.memory.enabled,
                "max_context_tokens": self.memory.max_context_tokens,
                "min_importance": self.memory.min_importance,
                "auto_extract": self.memory.auto_extract,
            },
            "thinking": {
                "enabled": self.thinking.enabled,
                "show_plan": self.thinking.show_plan,
                "save_plans": self.thinking.save_plans,
            },
            "workflow": {
                "auto_detect": self.workflow.auto_detect,
                "detection_threshold": self.workflow.detection_threshold,
                "interactive": self.workflow.interactive,
            },
            "agents": {
                "auto_spawn": self.agents.auto_spawn,
                "use_llm_classification": self.agents.use_llm_classification,
                "default_agent": self.agents.default_agent,
            },
            "autonomous": {
                "enabled": self.autonomous.enabled,
                "max_retries": self.autonomous.max_retries,
                "verification_enabled": self.autonomous.verification_enabled,
                "run_tests": self.autonomous.run_tests,
                "check_types": self.autonomous.check_types,
                "learning_enabled": self.autonomous.learning_enabled,
                "deep_analysis": self.autonomous.deep_analysis,
                "deep_reasoning": self.autonomous.deep_reasoning,
                "verbose": self.autonomous.verbose,
            },
            "personality": {
                "enabled": self.personality.enabled,
                "name": self.personality.name,
            },
        }

        if self.personality.custom_instructions:
            data["personality"]["custom_instructions"] = self.personality.custom_instructions

        if self.kira.model:
            data["kira"]["model"] = self.kira.model
        if self.default_skills:
            data["skills"] = self.default_skills
        if self.thinking.planning_model:
            data["thinking"]["planning_model"] = self.thinking.planning_model
        if self.workflow.default_skip_stages:
            data["workflow"]["default_skip_stages"] = self.workflow.default_skip_stages

        with open(self.USER_CONFIG_FILE, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
