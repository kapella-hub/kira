"""GitLab integration for project management and CI/CD."""

from .client import GitLabClient, GitLabError
from .models import GitLabConfig

__all__ = [
    "GitLabClient",
    "GitLabConfig",
    "GitLabError",
]
