"""SkillManager - Reusable workflow/prompt templates.

Skills are YAML files with:
- name: Skill identifier
- description: What the skill does
- prompt: The actual instructions/workflow

kiro-cli loads these via `skill://` resources. We manage the skill library.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A reusable skill definition."""

    name: str
    description: str
    prompt: str
    tags: list[str] = field(default_factory=list)
    path: Path | None = None

    @classmethod
    def from_yaml(cls, path: Path) -> Skill:
        """Load skill from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(
            name=data["name"],
            description=data["description"],
            prompt=data["prompt"],
            tags=data.get("tags", []),
            path=path,
        )

    def to_yaml(self) -> str:
        """Serialize skill to YAML."""
        return yaml.dump(
            {
                "name": self.name,
                "description": self.description,
                "tags": self.tags,
                "prompt": self.prompt,
            },
            default_flow_style=False,
            sort_keys=False,
        )

    def save(self, path: Path) -> None:
        """Save skill to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_yaml())
        self.path = path


class SkillManager:
    """Manages the skill library.

    Skills are stored as YAML files and can be:
    - Built-in (shipped with kira)
    - User-defined (in ~/.kira/agent/skills/)
    - Project-local (in .kira/skills/)
    """

    BUILTIN_DIR = Path(__file__).parent / "builtin"
    USER_DIR = Path.home() / ".kira" / "skills"
    LOCAL_DIR = Path(".kira") / "skills"

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self._skills: dict[str, Skill] = {}
        self._ensure_dirs()
        self._load_all()

    def _ensure_dirs(self) -> None:
        """Create skill directories if needed."""
        self.USER_DIR.mkdir(parents=True, exist_ok=True)

    def _load_all(self) -> None:
        """Load skills from all directories.

        Priority: project-local > user > builtin
        (later loads override earlier)
        """
        directories = [
            self.BUILTIN_DIR,
            self.USER_DIR,
            self.project_dir / ".kira" / "skills",
        ]

        for directory in directories:
            if directory.exists():
                for path in directory.glob("*.yaml"):
                    try:
                        skill = Skill.from_yaml(path)
                        self._skills[skill.name] = skill
                    except Exception as e:
                        logger.warning(f"Could not load skill {path}: {e}")

    def reload(self) -> None:
        """Reload all skills from disk."""
        self._skills.clear()
        self._load_all()

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_all(self, tags: list[str] | None = None) -> list[Skill]:
        """List all available skills."""
        skills = list(self._skills.values())
        if tags:
            skills = [s for s in skills if any(t in s.tags for t in tags)]
        return sorted(skills, key=lambda s: s.name)

    def add(
        self,
        name: str,
        description: str,
        prompt: str,
        tags: list[str] | None = None,
        local: bool = False,
    ) -> Skill:
        """Add a new skill."""
        directory = (self.project_dir / ".kira" / "skills") if local else self.USER_DIR
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"{name}.yaml"
        skill = Skill(
            name=name,
            description=description,
            prompt=prompt,
            tags=tags or [],
            path=path,
        )

        skill.save(path)
        self._skills[name] = skill
        return skill

    def remove(self, name: str) -> bool:
        """Remove a user-defined skill."""
        skill = self._skills.get(name)
        if not skill:
            return False

        if not skill.path:
            return False

        # Don't allow removing built-in skills
        try:
            if skill.path.is_relative_to(self.BUILTIN_DIR):
                raise ValueError(f"Cannot remove built-in skill: {name}")
        except ValueError:
            # is_relative_to raises ValueError if not relative
            pass

        skill.path.unlink()
        del self._skills[name]
        return True

    def is_builtin(self, name: str) -> bool:
        """Check if a skill is built-in."""
        skill = self._skills.get(name)
        if not skill or not skill.path:
            return False
        try:
            return skill.path.is_relative_to(self.BUILTIN_DIR)
        except ValueError:
            return False

    def get_prompt(self, name: str) -> str | None:
        """Get just the prompt text for a skill."""
        skill = self.get(name)
        return skill.prompt if skill else None
