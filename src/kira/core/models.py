"""Model aliases and resolution.

Models are fetched dynamically from kiro-cli when available,
with fallback to defaults if kiro-cli isn't installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Information about a model."""

    name: str
    display_name: str
    tier: str  # fast, smart, best
    description: str
    credit_multiplier: float = 1.0

    @classmethod
    def from_kiro_line(cls, line: str) -> ModelInfo | None:
        """Parse a model from kiro-cli output line.

        Expected format: "model-name | Nx credit | Description"
        """
        # Match: name | multiplier | description
        match = re.match(
            r"^\s*([a-zA-Z0-9._-]+)\s*\|\s*([\d.]+)x\s*credit\s*\|\s*(.+)$", line.strip()
        )
        if not match:
            return None

        name = match.group(1)
        credit = float(match.group(2))
        description = match.group(3).strip()

        # Determine tier from name
        tier = "smart"
        if "haiku" in name.lower():
            tier = "fast"
        elif "opus" in name.lower():
            tier = "best"

        # Generate display name
        display_name = name.replace("-", " ").title()
        display_name = display_name.replace("Claude ", "Claude ")

        return cls(
            name=name,
            display_name=display_name,
            tier=tier,
            description=description,
            credit_multiplier=credit,
        )


# Fallback models if kiro-cli isn't available
_FALLBACK_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="Auto",
        display_name="Auto",
        tier="smart",
        description="Models chosen by task for optimal usage",
        credit_multiplier=1.0,
    ),
    ModelInfo(
        name="claude-haiku-4.5",
        display_name="Claude Haiku 4.5",
        tier="fast",
        description="The latest Claude Haiku model",
        credit_multiplier=0.4,
    ),
    ModelInfo(
        name="claude-sonnet-4",
        display_name="Claude Sonnet 4",
        tier="smart",
        description="Hybrid reasoning and coding for regular use",
        credit_multiplier=1.3,
    ),
    ModelInfo(
        name="claude-sonnet-4.5",
        display_name="Claude Sonnet 4.5",
        tier="smart",
        description="The latest Claude Sonnet model",
        credit_multiplier=1.3,
    ),
    ModelInfo(
        name="claude-opus-4.5",
        display_name="Claude Opus 4.5",
        tier="best",
        description="The latest Claude Opus model",
        credit_multiplier=2.2,
    ),
]

# Cache for fetched models
_cached_models: list[ModelInfo] | None = None


def _fetch_models_from_kiro() -> list[ModelInfo] | None:
    """Fetch available models from kiro-cli.

    Note: kiro-cli doesn't currently have a models API.
    This function is ready for when one is added.

    Returns:
        List of ModelInfo or None if fetch failed/not available.
    """
    # kiro-cli doesn't have a models subcommand yet
    # When it does, we can parse the output here
    # For now, return None to use fallback
    return None


def get_available_models(refresh: bool = False) -> list[ModelInfo]:
    """Get list of available models.

    Fetches from kiro-cli if available, otherwise uses fallback.
    Results are cached after first fetch.

    Args:
        refresh: Force refresh from kiro-cli.

    Returns:
        List of ModelInfo objects.
    """
    global _cached_models

    if _cached_models is None or refresh:
        fetched = _fetch_models_from_kiro()
        _cached_models = fetched or _FALLBACK_MODELS.copy()

    return _cached_models


def _build_aliases() -> dict[str, str]:
    """Build model aliases from available models."""
    models = get_available_models()
    aliases: dict[str, str] = {}

    # Find models by tier - prefer latest versions (higher version numbers)
    haikus = [m for m in models if "haiku" in m.name.lower()]
    sonnets = [m for m in models if "sonnet" in m.name.lower()]
    opuses = [m for m in models if "opus" in m.name.lower()]

    # Sort by version (e.g., 4.5 > 4) - latest first
    def version_key(m: ModelInfo) -> float:
        import re

        match = re.search(r"(\d+\.?\d*)", m.name)
        return float(match.group(1)) if match else 0

    haikus.sort(key=version_key, reverse=True)
    sonnets.sort(key=version_key, reverse=True)
    opuses.sort(key=version_key, reverse=True)

    # Speed tier - latest haiku
    if haikus:
        aliases["fast"] = haikus[0].name
        aliases["quick"] = haikus[0].name
        aliases["haiku"] = haikus[0].name

    # Balanced tier - latest sonnet
    if sonnets:
        aliases["smart"] = sonnets[0].name
        aliases["default"] = sonnets[0].name
        aliases["sonnet"] = sonnets[0].name

    # Best tier - latest opus
    if opuses:
        aliases["best"] = opuses[0].name
        aliases["opus"] = opuses[0].name

    # Auto
    auto = next((m for m in models if m.name.lower() == "auto"), None)
    if auto:
        aliases["auto"] = auto.name

    return aliases


# Build aliases on first access
_cached_aliases: dict[str, str] | None = None


def get_aliases() -> dict[str, str]:
    """Get model aliases."""
    global _cached_aliases
    if _cached_aliases is None:
        _cached_aliases = _build_aliases()
    return _cached_aliases


def resolve_model(model_name: str | None) -> str | None:
    """Resolve model alias to actual model name.

    Args:
        model_name: Alias or direct model name (e.g., "fast", "claude-opus-4.5")

    Returns:
        Resolved model name, or None if input was None
    """
    if model_name is None:
        return None

    # Check if it's an alias
    aliases = get_aliases()
    resolved = aliases.get(model_name.lower())
    if resolved:
        return resolved

    # Return as-is (assume it's a direct model name)
    return model_name


def list_aliases() -> list[tuple[str, str]]:
    """List all available model aliases.

    Returns:
        List of (alias, model_name) tuples
    """
    return sorted(get_aliases().items(), key=lambda x: x[1])


def get_tier(model_name: str) -> str:
    """Get the tier (fast/smart/best) for a model.

    Args:
        model_name: Model name or alias

    Returns:
        Tier name
    """
    resolved = resolve_model(model_name)
    if resolved:
        if "haiku" in resolved.lower():
            return "fast"
        elif "opus" in resolved.lower():
            return "best"
    return "smart"


def get_model_info(model_name: str) -> ModelInfo | None:
    """Get info for a specific model.

    Args:
        model_name: Model name or alias

    Returns:
        ModelInfo or None if not found
    """
    resolved = resolve_model(model_name)
    for model in get_available_models():
        if model.name == resolved or model.name.lower() == (resolved or "").lower():
            return model
    return None


def refresh_models() -> list[ModelInfo]:
    """Force refresh models from kiro-cli.

    Returns:
        Updated list of models.
    """
    global _cached_aliases
    _cached_aliases = None
    return get_available_models(refresh=True)
