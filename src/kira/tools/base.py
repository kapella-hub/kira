"""Base class for tools."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ToolCall, ToolContext, ToolResult, ToolStatus


class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str = "base"
    description: str = "Base tool"
    requires_trust: bool = False

    def __init__(self, context: ToolContext):
        """Initialize tool with context.

        Args:
            context: Tool execution context.
        """
        self.context = context

    @abstractmethod
    async def execute(self, **kwargs: str | int | bool | list[str] | None) -> ToolResult:
        """Execute the tool.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            Result of the tool execution.
        """
        pass

    def can_execute(self) -> tuple[bool, str]:
        """Check if tool can be executed in current context.

        Returns:
            Tuple of (can_execute, reason).
        """
        if self.requires_trust and self.context.trust_level == "restricted":
            return False, f"Tool {self.name} requires trust level"
        return True, ""

    def record(self, kwargs: dict[str, str | int | bool | list[str] | None], result: ToolResult) -> None:
        """Record tool execution."""
        call = ToolCall(tool_name=self.name, arguments=kwargs)
        self.context.record_call(call, result)

    def make_result(
        self,
        status: ToolStatus,
        output: str,
        error: str | None = None,
        files_modified: list[str] | None = None,
        files_created: list[str] | None = None,
        duration: float = 0.0,
    ) -> ToolResult:
        """Create a ToolResult.

        Args:
            status: Execution status.
            output: Tool output.
            error: Error message if any.
            files_modified: List of modified files.
            files_created: List of created files.
            duration: Execution duration in seconds.

        Returns:
            ToolResult instance.
        """
        return ToolResult(
            tool_name=self.name,
            status=status,
            output=output,
            error=error,
            duration_seconds=duration,
            files_modified=files_modified or [],
            files_created=files_created or [],
        )


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, type[BaseTool]] = {}

    def register(self, tool_class: type[BaseTool]) -> type[BaseTool]:
        """Register a tool class.

        Args:
            tool_class: Tool class to register.

        Returns:
            The registered tool class (for decorator use).
        """
        self._tools[tool_class.name] = tool_class
        return tool_class

    def get(self, name: str) -> type[BaseTool] | None:
        """Get a tool class by name.

        Args:
            name: Tool name.

        Returns:
            Tool class or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def create(self, name: str, context: ToolContext) -> BaseTool | None:
        """Create a tool instance.

        Args:
            name: Tool name.
            context: Tool context.

        Returns:
            Tool instance or None if not found.
        """
        tool_class = self.get(name)
        if tool_class:
            return tool_class(context)
        return None


# Global registry
registry = ToolRegistry()
