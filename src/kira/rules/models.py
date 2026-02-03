"""Data models for the rules system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RuleCategory(Enum):
    """Categories of rules."""

    CODING = "coding"
    REFACTORING = "refactoring"
    UI_DESIGN = "ui-design"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


@dataclass
class Rule:
    """A single rule or guideline."""

    text: str
    priority: int = 5  # 1-10, higher = more important
    category: str = ""


@dataclass
class RuleSet:
    """A collection of related rules."""

    name: str
    category: RuleCategory
    description: str = ""
    triggers: list[str] = field(default_factory=list)  # Keywords that activate this ruleset
    rules: list[Rule] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)  # What to avoid
    principles: list[str] = field(default_factory=list)  # High-level guiding principles
    examples: dict[str, str] = field(default_factory=dict)  # good/bad examples

    def matches_task(self, task: str) -> bool:
        """Check if this ruleset applies to the given task."""
        task_lower = task.lower()
        return any(trigger.lower() in task_lower for trigger in self.triggers)

    def to_prompt(self, max_rules: int = 10) -> str:
        """Format ruleset for injection into prompts."""
        parts = [f"## {self.name}"]

        if self.description:
            parts.append(f"\n{self.description}\n")

        if self.principles:
            parts.append("\n### Guiding Principles")
            for principle in self.principles[:5]:
                parts.append(f"- {principle}")

        if self.rules:
            parts.append("\n### Rules")
            # Sort by priority (highest first) and take top N
            sorted_rules = sorted(self.rules, key=lambda r: r.priority, reverse=True)
            for rule in sorted_rules[:max_rules]:
                parts.append(f"- {rule.text}")

        if self.anti_patterns:
            parts.append("\n### Anti-patterns (avoid these)")
            for anti in self.anti_patterns[:5]:
                parts.append(f"- {anti}")

        return "\n".join(parts)
