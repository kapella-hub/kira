"""Integrations module for external services."""

from . import jira

__all__ = ["jira"]

# Optional integrations - import without failing
try:
    from . import chalk  # noqa: F401

    __all__.append("chalk")
except ImportError:
    pass

try:
    from . import gitlab  # noqa: F401

    __all__.append("gitlab")
except ImportError:
    pass
