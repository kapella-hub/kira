"""Output formatter for rendering markdown with enhanced code blocks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.box import ROUNDED
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

if TYPE_CHECKING:
    pass


# Language aliases for syntax highlighting
LANGUAGE_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "rb": "ruby",
    "sh": "bash",
    "shell": "bash",
    "yml": "yaml",
    "dockerfile": "docker",
}

# Patterns that indicate kiro-cli tool output (not response content)
TOOL_OUTPUT_PATTERNS = [
    # Tool invocation: "something (using tool: toolname)"
    re.compile(r"\(using tool: \w+\)"),
    # Status indicators at start of line
    re.compile(r"^[\s]*[↱✓⋮]"),
    # Completed timing: " - Completed in X.XXs"
    re.compile(r"^\s*-\s*Completed in"),
    # Summary line
    re.compile(r"^\s*-\s*Summary:"),
    # Metadata in brackets at start: "[Overview]", "[Error]", etc.
    re.compile(r"^\s*\[\w+\]"),
    # Batch operations
    re.compile(r"^Batch \w+ operation"),
    # Operation status lines
    re.compile(r"^\s*Operation \d+:"),
    # Reading/Writing file status
    re.compile(r"^\s*(Reading|Writing|Searching|Executing)"),
]


class OutputFormatter:
    """Formats markdown output with enhanced code block rendering.

    Handles kiro-cli output which contains:
    1. Tool execution status (passed through as-is)
    2. Response content (formatted with markdown/syntax highlighting)
    """

    # Pattern to match fenced code blocks
    CODE_BLOCK_PATTERN = re.compile(
        r"```(\w+)?[ \t]*\n(.*?)```",
        re.DOTALL,
    )

    def __init__(self, console: Console | None = None, theme: str = "monokai"):
        """Initialize the formatter.

        Args:
            console: Rich console for output. Creates new if not provided.
            theme: Syntax highlighting theme name.
        """
        self.console = console or Console()
        self.theme = theme

    def format(self, text: str) -> None:
        """Parse and render output with proper formatting.

        Separates tool output (passed through) from response content (formatted).

        Args:
            text: Raw output text from kiro-cli.
        """
        if not text or not text.strip():
            return

        # Split into tool output and response content
        tool_output, response_content = self._split_tool_and_response(text)

        # Print tool output as-is (already formatted by kiro-cli)
        if tool_output.strip():
            self.console.print(tool_output, highlight=False)

        # Format and print response content
        if response_content.strip():
            self._format_response(response_content)

    def _split_tool_and_response(self, text: str) -> tuple[str, str]:
        """Split text into tool output and response content.

        Tool output includes status lines from kiro-cli tools.
        Response content is the actual markdown response.

        Args:
            text: Raw output text.

        Returns:
            Tuple of (tool_output, response_content).
        """
        lines = text.split("\n")
        tool_lines = []
        response_lines = []
        in_response = False

        for line in lines:
            if in_response:
                response_lines.append(line)
            elif self._is_tool_output(line):
                tool_lines.append(line)
            else:
                # Check if this looks like the start of real content
                stripped = line.strip()
                if stripped and not self._is_tool_output(line):
                    # Start of response content
                    in_response = True
                    response_lines.append(line)
                else:
                    tool_lines.append(line)

        return "\n".join(tool_lines), "\n".join(response_lines)

    def _is_tool_output(self, line: str) -> bool:
        """Check if a line is tool execution output.

        Args:
            line: Line to check.

        Returns:
            True if line is tool output, False otherwise.
        """
        # Empty or whitespace-only lines in tool section
        if not line.strip():
            return True

        # Check against tool output patterns
        for pattern in TOOL_OUTPUT_PATTERNS:
            if pattern.search(line):
                return True

        return False

    def _format_response(self, text: str) -> None:
        """Format response content with markdown and code blocks.

        Args:
            text: Response content to format.
        """
        # Split text into code blocks and other content
        parts = self._split_content(text)

        for part in parts:
            if part["type"] == "code":
                self._render_code_block(part)
            else:
                self._render_markdown(part["content"])

    def _split_content(self, text: str) -> list[dict]:
        """Split text into code blocks and markdown sections.

        Returns:
            List of dicts with 'type' ('code' or 'markdown') and content.
        """
        parts = []
        last_end = 0

        for match in self.CODE_BLOCK_PATTERN.finditer(text):
            # Add markdown content before this code block
            before = text[last_end : match.start()]
            if before.strip():
                parts.append({"type": "markdown", "content": before})

            # Extract code block details
            language = match.group(1) or ""
            code = match.group(2)

            # Normalize language name
            language = LANGUAGE_ALIASES.get(language.lower(), language.lower())

            # Try to extract file path from first line
            file_path = None
            lines = code.split("\n")
            if lines:
                file_path = self._extract_file_path(lines[0], language)
                if file_path:
                    # Remove the file path line from code
                    code = "\n".join(lines[1:])

            # Clean up code (remove trailing whitespace but preserve structure)
            code = code.rstrip()

            parts.append(
                {
                    "type": "code",
                    "language": language or "text",
                    "code": code,
                    "file_path": file_path,
                }
            )

            last_end = match.end()

        # Add remaining markdown content
        after = text[last_end:]
        if after.strip():
            parts.append({"type": "markdown", "content": after})

        return parts

    def _extract_file_path(self, line: str, language: str) -> str | None:
        """Extract file path from the first line of a code block.

        Looks for common comment patterns like:
        - // path/to/file.ts
        - # path/to/file.py
        - <!-- path/to/file.html -->

        Args:
            line: First line of the code block.
            language: Programming language of the code block.

        Returns:
            File path if found, None otherwise.
        """
        line = line.strip()
        if not line:
            return None

        # Comment patterns for different languages
        comment_patterns = [
            # // path/to/file.ext
            re.compile(r"^//\s*(.+?\.\w+)\s*$"),
            # # path/to/file.ext
            re.compile(r"^#\s*([a-zA-Z0-9_./\\-]+\.\w+)\s*$"),
            # -- path/to/file.ext
            re.compile(r"^--\s*(.+?\.\w+)\s*$"),
            # /* path/to/file.ext */
            re.compile(r"^/\*\s*(.+?\.\w+)\s*\*/\s*$"),
            # <!-- path/to/file.html -->
            re.compile(r"^<!--\s*(.+?\.\w+)\s*-->?\s*$"),
        ]

        for pattern in comment_patterns:
            match = pattern.match(line)
            if match:
                path = match.group(1).strip()
                # Validate it looks like a file path
                if "/" in path or "\\" in path or "." in path:
                    return path

        # Also check for plain file path patterns without comment markers
        # e.g., "src/utils/helper.ts" or "file: path/to/file.py"
        file_pattern = re.match(r"^(?:file:\s*)?([a-zA-Z0-9_./\\-]+\.\w+)\s*$", line)
        if file_pattern:
            return file_pattern.group(1)

        return None

    def _render_code_block(self, block: dict) -> None:
        """Render a code block with syntax highlighting and line numbers.

        Args:
            block: Dict with 'code', 'language', and optional 'file_path'.
        """
        code = block["code"]
        language = block.get("language", "text")
        file_path = block.get("file_path")

        # Skip empty code blocks
        if not code.strip():
            return

        # Create syntax object with line numbers
        try:
            syntax = Syntax(
                code,
                language,
                line_numbers=True,
                theme=self.theme,
                word_wrap=True,
                background_color="default",
            )
        except Exception:
            # Fall back to plain text if language not supported
            syntax = Syntax(
                code,
                "text",
                line_numbers=True,
                theme=self.theme,
                word_wrap=True,
                background_color="default",
            )

        if file_path:
            # Show in panel with file path as title
            panel = Panel(
                syntax,
                title=f"[bold cyan]{file_path}[/]",
                title_align="left",
                border_style="dim",
                box=ROUNDED,
                padding=(0, 1),
            )
            self.console.print(panel)
        else:
            # Just show syntax with a subtle border
            panel = Panel(
                syntax,
                border_style="dim",
                box=ROUNDED,
                padding=(0, 1),
            )
            self.console.print(panel)

    def _render_markdown(self, content: str) -> None:
        """Render markdown content.

        Args:
            content: Markdown text to render.
        """
        content = content.strip()
        if not content:
            return

        # Use Rich's markdown renderer
        md = Markdown(content)
        self.console.print(md)


def format_output(text: str, console: Console | None = None) -> None:
    """Convenience function to format and print markdown output.

    Args:
        text: Raw output text from kiro-cli.
        console: Optional Rich console instance.
    """
    formatter = OutputFormatter(console)
    formatter.format(text)
