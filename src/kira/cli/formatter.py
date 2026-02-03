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

# Box drawing and ASCII art characters that should be preserved
ASCII_ART_CHARS = set("│┌┐└┘├┤┬┴┼─═║╔╗╚╝╠╣╦╩╬▀▄█▌▐░▒▓■□▪▫●○◆◇★☆►◄▲▼←→↑↓↔↕")

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

    # Pattern to match fenced code blocks (```lang ... ```)
    CODE_BLOCK_PATTERN = re.compile(
        r"```(\w+)?[ \t]*\n(.*?)```",
        re.DOTALL,
    )

    # Pattern to match unfenced code blocks (language name on its own line followed by code)
    # e.g., "typescript\ninterface User { ... }"
    UNFENCED_CODE_PATTERN = re.compile(
        r"^(typescript|javascript|python|java|go|rust|ruby|sql|bash|shell|json|yaml|html|css|c|cpp|csharp|php|swift|kotlin)\n((?:[ \t].*\n?|[a-zA-Z_].*[{(\[].*\n?)+)",
        re.MULTILINE | re.IGNORECASE,
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
        # Pre-process to convert inline code patterns to fenced blocks
        text = self._convert_inline_code(text)

        # Split text into code blocks and other content
        parts = self._split_content(text)

        for part in parts:
            if part["type"] == "code":
                self._render_code_block(part)
            else:
                self._render_markdown(part["content"])

    def _convert_inline_code(self, text: str) -> str:
        """Convert inline code patterns to fenced code blocks.

        Detects patterns like:
        - json { ... }  (language followed by inline code)
        - Request: { ... } Response: { ... }

        Args:
            text: Text to process.

        Returns:
            Text with inline code converted to fenced blocks.
        """
        import json as json_mod

        def extract_json_object(text: str, start: int) -> tuple[str, int] | None:
            """Extract a complete JSON object handling nested braces."""
            if start >= len(text) or text[start] != "{":
                return None
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                c = text[i]
                if escape:
                    escape = False
                    continue
                if c == "\\" and in_string:
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : i + 1], i + 1
            return None

        def format_json(code: str) -> str:
            """Try to pretty-format JSON."""
            try:
                parsed = json_mod.loads(code)
                return json_mod.dumps(parsed, indent=2)
            except:
                return code

        # Pattern: language name followed by { on same line
        # e.g., "json { "key": "value" }"
        inline_lang = re.compile(r"\b(json|javascript|python|typescript)\s*\{", re.IGNORECASE)

        lines = text.split("\n")
        new_lines = []

        for line in lines:
            # Check for "json {" pattern
            match = inline_lang.search(line)
            if match:
                lang = match.group(1).lower()
                json_start = match.end() - 1  # Position of {
                extracted = extract_json_object(line, json_start)
                if extracted:
                    code, end_pos = extracted
                    before = line[: match.start()]
                    after = line[end_pos:]
                    formatted = format_json(code)
                    new_lines.append(before.rstrip())
                    new_lines.append(f"```{lang}")
                    new_lines.append(formatted)
                    new_lines.append("```")
                    if after.strip():
                        new_lines.append(after.lstrip())
                    continue

            # Check for "Request: {" or "Response 201: {" pattern
            req_match = re.search(r"(Request|Response(?:\s+\d+)?)\s*:\s*\{", line, re.IGNORECASE)
            if req_match:
                label = req_match.group(1)
                json_start = req_match.end() - 1
                extracted = extract_json_object(line, json_start)
                if extracted:
                    code, end_pos = extracted
                    before = line[: req_match.start()]
                    after = line[end_pos:]
                    formatted = format_json(code)
                    if before.strip():
                        new_lines.append(before.rstrip())
                    new_lines.append(f"**{label}:**")
                    new_lines.append("```json")
                    new_lines.append(formatted)
                    new_lines.append("```")
                    if after.strip():
                        new_lines.append(after.lstrip())
                    continue

            new_lines.append(line)

        return "\n".join(new_lines)

    def _split_content(self, text: str) -> list[dict]:
        """Split text into code blocks and markdown sections.

        Returns:
            List of dicts with 'type' ('code' or 'markdown') and content.
        """
        # First, convert unfenced code blocks to fenced ones
        text = self._convert_unfenced_code_blocks(text)

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

    def _convert_unfenced_code_blocks(self, text: str) -> str:
        """Convert unfenced code blocks to fenced format.

        Detects patterns where a language name appears alone on a line
        followed by code (common in kiro-cli output).

        Args:
            text: Text to process.

        Returns:
            Text with unfenced code blocks converted to fenced.
        """
        lines = text.split("\n")
        result = []
        i = 0

        # Known language keywords
        languages = {
            "typescript",
            "javascript",
            "python",
            "java",
            "go",
            "rust",
            "ruby",
            "sql",
            "bash",
            "shell",
            "json",
            "yaml",
            "html",
            "css",
            "c",
            "cpp",
            "csharp",
            "php",
            "swift",
            "kotlin",
            "scala",
            "mermaid",
            "markdown",
            "md",
            "xml",
            "toml",
            "ini",
            "dockerfile",
            "makefile",
            "cmake",
            "gradle",
            "graphql",
            "proto",
            "protobuf",
        }

        def looks_like_code(line: str, lang: str) -> bool:
            """Check if a line looks like code for the given language."""
            stripped = line.strip()
            if not stripped:
                return False

            # Indented lines are usually code
            if line.startswith("    ") or line.startswith("\t"):
                return True

            # Definitely code patterns
            code_patterns = [
                r"^#!",  # Shebang
                r"^(interface|class|function|def|const|let|var|import|export|from|type|enum)\b",
                r"^(public|private|protected|static|async|await)\b",
                r"^\s*[{}\[\]()]",
                r"^[a-zA-Z_]\w*\s*[(={:]",
                r"^\s*//|^\s*/\*",  # C-style comments
                r"^#\s*\w",  # Shell/Python comments (# followed by word char)
                r"=>|->|\|\||&&",
                r"^\s*@\w+",  # Decorators
                r"^\s*self\.",  # Python self
                r"^\s*return\b",
                r"^\s*(if|for|while|try|except|with)\b.*:",
                # Shell patterns
                r"^[A-Z_][A-Z0-9_]*=",  # Shell variable assignment (THRESHOLD=90)
                r"^\s*(echo|printf|read|exit|source|chmod|chown|mkdir|rm|cp|mv|cat|grep|awk|sed|sudo)\b",
                r"^\s*(fi|done|esac|then|else|elif|do)\b",  # Shell keywords
                r"^\s*\[\[?\s",  # Shell test brackets
                r"^\$\(",  # Command substitution
                r"^\s*(while|for|if|until)\s+.*;\s*do",  # Shell loops: while true; do
                r"^\s*(if|elif)\s+\[",  # Shell conditionals: if [ ... ]
                r"sleep\s+\d",  # sleep command
                # Mermaid patterns
                r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey)\b",
                r"^\s*[A-Z]\[",  # Mermaid node: A[text]
                r"^\s*[A-Z]\s*-->",  # Mermaid arrow: A --> B
                r"^\s*participant\b",  # Mermaid sequence diagram
                # SQL patterns
                r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|GROUP|ORDER|HAVING|LIMIT|OFFSET|UNION|SET|VALUES)\b",
                # GraphQL patterns
                r"^\s*(query|mutation|subscription|type|input|enum|interface|fragment)\b",
                # Go patterns
                r"^package\s+\w+",
                r'^import\s+[(""]',
                r"^func\s+\w*\s*\(",
                r"^(var|const)\s+\w+",
                r"^\s*defer\s+",
                # Rust patterns
                r"^(fn|let|mut|pub|mod|use|impl|struct|trait|enum|match)\s+",
                r"^\s*println!\s*\(",
                r"^#\[",  # Rust attributes
                # YAML patterns (key: value at start, or just key:)
                r"^[a-zA-Z_][a-zA-Z0-9_-]*:\s*$",  # key: (alone on line)
                r"^[a-zA-Z_][a-zA-Z0-9_-]*:\s*\S",  # key: value
                r"^\s+-\s+\w",  # YAML list items
                r"^\s+[a-zA-Z_][a-zA-Z0-9_-]*:",  # Indented key:
                # Dockerfile patterns
                r"^(FROM|RUN|CMD|COPY|ADD|WORKDIR|ENV|EXPOSE|ENTRYPOINT|ARG|LABEL|USER|VOLUME)\s+",
                # Makefile patterns
                r"^[a-zA-Z_][a-zA-Z0-9_]*\s*:(?!=)",  # target: (not :=)
                r"^\t+\w",  # Tab-indented commands
            ]

            for pattern in code_patterns:
                if re.search(pattern, line):
                    return True

            return False

        def looks_like_prose(line: str) -> bool:
            """Check if a line looks like prose/markdown."""
            stripped = line.strip()
            if not stripped:
                return True  # Empty lines end code blocks

            # Code patterns that should NOT be treated as prose
            # even if they end with a colon (Python class/def/if/etc.)
            code_intro_patterns = [
                r"^#!",  # Shebang
                r"^(class|def|if|elif|else|for|while|with|try|except|finally|async|match|case)\b",
                r"^(interface|type|enum|function|const|let|var|export|import)\b",
                r"^(public|private|protected|static)\b",
                r"^\s*@\w+",  # Decorators
                # Shell patterns
                r"^[A-Z_][A-Z0-9_]*=",  # Variable assignment
                r"^(echo|printf|sudo|chmod|fi|done|esac|then|do)\b",
                r"^#\s*[a-z_]",  # Shell comment (lowercase after #, not markdown header)
            ]
            for pattern in code_intro_patterns:
                if re.search(pattern, stripped, re.IGNORECASE):
                    return False

            # Prose patterns
            prose_patterns = [
                r"^(And|Or|But|If|The|This|That|Here|Now|Also|Want|Why|How|What)\s",
                r"^[A-Z][a-z]+\s+[a-z]+\s+[a-z]+",  # "Common additions depending"
                r"^\*\s",  # Markdown list
                r"^-\s+[A-Z]",  # Markdown list with capital
                r"^#+\s",  # Markdown header
                r"^.{15,}:\s*$",  # Ends with colon but has significant text (prose intro)
            ]

            for pattern in prose_patterns:
                if re.search(pattern, stripped):
                    return True

            return False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip().lower()

            # Check if this line is just a language name
            if stripped in languages and i + 1 < len(lines):
                # Look ahead to see if next lines look like code
                code_lines = []
                j = i + 1

                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.strip()

                    # Handle empty lines - look ahead to see if more code follows
                    if not next_stripped:
                        # Check if there's more code after this empty line
                        lookahead = j + 1
                        found_more_code = False
                        while lookahead < len(lines) and lookahead < j + 3:
                            ahead_line = lines[lookahead]
                            if ahead_line.strip():
                                if (
                                    looks_like_code(ahead_line, stripped)
                                    or ahead_line.startswith("    ")
                                    or ahead_line.startswith("\t")
                                ):
                                    found_more_code = True
                                break
                            lookahead += 1

                        if found_more_code:
                            code_lines.append(next_line)
                            j += 1
                            continue
                        else:
                            break  # Empty line followed by prose or nothing

                    # Stop at prose-like lines (but not empty ones - handled above)
                    if looks_like_prose(next_line):
                        break

                    # Accept code-like lines or continuation
                    if (
                        looks_like_code(next_line, stripped)
                        or next_line.startswith("  ")
                        or next_line.startswith("\t")
                        or re.match(r"^\s*[}\])]", next_line)
                    ):
                        code_lines.append(next_line)
                        j += 1
                    else:
                        # Check if it's a closing brace
                        if next_stripped in ["}", "]", ")"]:
                            code_lines.append(next_line)
                            j += 1
                        break

                # Remove trailing empty lines from code
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()

                if code_lines:
                    # Found code block - convert to fenced
                    result.append(f"```{stripped}")
                    result.extend(code_lines)
                    result.append("```")
                    i = j
                    continue

            result.append(line)
            i += 1

        return "\n".join(result)

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
        """Render markdown content, preserving ASCII art.

        Args:
            content: Markdown text to render.
        """
        content = content.strip()
        if not content:
            return

        # Split content and handle ASCII art sections separately
        sections = self._split_ascii_art(content)

        for section in sections:
            if section["type"] == "ascii_art":
                # Print ASCII art as-is to preserve formatting
                self.console.print(section["content"], highlight=False)
            elif section["type"] == "markdown":
                # Use Rich's markdown renderer
                text = section["content"].strip()
                if text:
                    md = Markdown(text)
                    self.console.print(md)

    def _split_ascii_art(self, content: str) -> list[dict]:
        """Split content into ASCII art and markdown sections.

        Args:
            content: Text content to split.

        Returns:
            List of dicts with 'type' ('ascii_art' or 'markdown') and 'content'.
        """
        lines = content.split("\n")
        sections = []
        current_type = None
        current_lines = []

        for line in lines:
            is_ascii = self._is_ascii_art_line(line)
            line_type = "ascii_art" if is_ascii else "markdown"

            if current_type is None:
                current_type = line_type
                current_lines = [line]
            elif line_type == current_type:
                current_lines.append(line)
            else:
                # Type changed, save current section
                if current_lines:
                    sections.append(
                        {
                            "type": current_type,
                            "content": "\n".join(current_lines),
                        }
                    )
                current_type = line_type
                current_lines = [line]

        # Don't forget the last section
        if current_lines:
            sections.append(
                {
                    "type": current_type,
                    "content": "\n".join(current_lines),
                }
            )

        return sections

    def _is_ascii_art_line(self, line: str) -> bool:
        """Check if a line contains ASCII art characters.

        Args:
            line: Line to check.

        Returns:
            True if line appears to be ASCII art.
        """
        if not line.strip():
            return False

        # Check if line contains box drawing or ASCII art characters
        ascii_count = sum(1 for c in line if c in ASCII_ART_CHARS)

        # If more than 2 ASCII art characters, treat as ASCII art
        # This helps preserve org charts, tables, diagrams
        return ascii_count >= 2


def format_output(text: str, console: Console | None = None) -> None:
    """Convenience function to format and print markdown output.

    Args:
        text: Raw output text from kiro-cli.
        console: Optional Rich console instance.
    """
    formatter = OutputFormatter(console)
    formatter.format(text)
