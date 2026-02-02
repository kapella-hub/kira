"""Output formatter for rendering markdown with enhanced code blocks."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

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

# Comment patterns for different languages to extract file paths
COMMENT_PATTERNS = {
    # // path/to/file.ext
    "slash": re.compile(r"^//\s*(.+?\.\w+)\s*$"),
    # # path/to/file.ext
    "hash": re.compile(r"^#\s*(.+?\.\w+)\s*$"),
    # -- path/to/file.ext
    "dash": re.compile(r"^--\s*(.+?\.\w+)\s*$"),
    # /* path/to/file.ext */
    "block": re.compile(r"^/\*\s*(.+?\.\w+)\s*\*/\s*$"),
    # <!-- path/to/file.ext -->
    "html": re.compile(r"^<!--\s*(.+?\.\w+)\s*-->?\s*$"),
}


class OutputFormatter:
    """Formats markdown output with enhanced code block rendering.

    Features:
    - Syntax highlighting for code blocks
    - Line numbers
    - File path detection and display as headers
    - Proper markdown rendering for non-code content
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
        """Parse and render markdown with enhanced code blocks.

        Args:
            text: Markdown text to render.
        """
        if not text or not text.strip():
            return

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

        # Try each comment pattern
        for pattern in COMMENT_PATTERNS.values():
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
        text: Markdown text to render.
        console: Optional Rich console instance.
    """
    formatter = OutputFormatter(console)
    formatter.format(text)
