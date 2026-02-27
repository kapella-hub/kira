"""Kira: Agent Kanban Board with worker-based execution."""

try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("kira")
except Exception:
    __version__ = "0.3.0-dev"
