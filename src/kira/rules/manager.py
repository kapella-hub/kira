"""RulesManager - Loads and manages coding rules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .models import Rule, RuleCategory, RuleSet

if TYPE_CHECKING:
    pass


class RulesManager:
    """Manages loading and applying coding rules.

    Rules are loaded from:
    1. Built-in rules (shipped with kira)
    2. User rules (~/.kira/rules/)
    3. Project rules (.kira/rules/)

    Project rules override user rules, which override built-in rules.
    """

    def __init__(self, working_dir: Path | None = None):
        self.working_dir = working_dir or Path.cwd()
        self._rulesets: dict[str, RuleSet] = {}
        self._loaded = False

    @property
    def builtin_dir(self) -> Path:
        """Directory containing built-in rules."""
        return Path(__file__).parent / "builtin"

    @property
    def user_dir(self) -> Path:
        """Directory containing user rules."""
        return Path.home() / ".kira" / "rules"

    @property
    def project_dir(self) -> Path:
        """Directory containing project rules."""
        return self.working_dir / ".kira" / "rules"

    def load(self) -> None:
        """Load all rules from all sources."""
        if self._loaded:
            return

        # Load in order: builtin -> user -> project (later overrides earlier)
        for rules_dir in [self.builtin_dir, self.user_dir, self.project_dir]:
            if rules_dir.exists():
                self._load_from_directory(rules_dir)

        self._loaded = True

    def _load_from_directory(self, directory: Path) -> None:
        """Load all rule files from a directory."""
        for file_path in directory.glob("*.yaml"):
            try:
                ruleset = self._parse_ruleset(file_path)
                if ruleset:
                    # Use category as key, allowing overrides
                    self._rulesets[ruleset.category.value] = ruleset
            except Exception as e:
                # Log but don't fail on bad rule files
                print(f"Warning: Failed to load rules from {file_path}: {e}")

    def _parse_ruleset(self, file_path: Path) -> RuleSet | None:
        """Parse a YAML file into a RuleSet."""
        with open(file_path) as f:
            data = yaml.safe_load(f)

        if not data:
            return None

        # Determine category from filename or explicit field
        category_str = data.get("category", file_path.stem)
        try:
            category = RuleCategory(category_str)
        except ValueError:
            category = RuleCategory.CUSTOM

        # Parse rules
        rules = []
        for rule_data in data.get("rules", []):
            if isinstance(rule_data, str):
                rules.append(Rule(text=rule_data))
            elif isinstance(rule_data, dict):
                rules.append(
                    Rule(
                        text=rule_data.get("text", ""),
                        priority=rule_data.get("priority", 5),
                        category=rule_data.get("category", ""),
                    )
                )

        return RuleSet(
            name=data.get("name", file_path.stem.replace("-", " ").title()),
            category=category,
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            rules=rules,
            anti_patterns=data.get("anti_patterns", []),
            principles=data.get("principles", []),
            examples=data.get("examples", {}),
        )

    def get_ruleset(self, category: str | RuleCategory) -> RuleSet | None:
        """Get a specific ruleset by category."""
        self.load()
        if isinstance(category, RuleCategory):
            category = category.value
        return self._rulesets.get(category)

    def get_matching_rulesets(self, task: str) -> list[RuleSet]:
        """Get all rulesets that match the given task."""
        self.load()
        return [rs for rs in self._rulesets.values() if rs.matches_task(task)]

    def get_all_rulesets(self) -> list[RuleSet]:
        """Get all loaded rulesets."""
        self.load()
        return list(self._rulesets.values())

    def get_context(self, task: str, max_rulesets: int = 3) -> str:
        """Get rules context for a task.

        Returns formatted rules for injection into prompts.
        """
        matching = self.get_matching_rulesets(task)

        if not matching:
            return ""

        # Limit number of rulesets to avoid prompt bloat
        matching = matching[:max_rulesets]

        parts = ["## Coding Rules & Guidelines\n"]
        for ruleset in matching:
            parts.append(ruleset.to_prompt())
            parts.append("")  # Blank line between rulesets

        return "\n".join(parts)

    def list_categories(self) -> list[str]:
        """List all available rule categories."""
        self.load()
        return list(self._rulesets.keys())


# Global instance for convenience
_rules_manager: RulesManager | None = None


def get_rules_manager(working_dir: Path | None = None) -> RulesManager:
    """Get the global rules manager instance."""
    global _rules_manager
    if _rules_manager is None or (working_dir and _rules_manager.working_dir != working_dir):
        _rules_manager = RulesManager(working_dir)
    return _rules_manager
