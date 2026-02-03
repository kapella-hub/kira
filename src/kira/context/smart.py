"""Smart context loading - auto-detect relevant files from task."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ContextMatch:
    """A matched file with relevance info."""

    path: Path
    relevance: float  # 0.0 - 1.0
    match_reason: str
    preview: str = ""  # First few lines or matched section


@dataclass
class SmartContext:
    """Result of smart context detection."""

    matches: list[ContextMatch] = field(default_factory=list)
    keywords_found: list[str] = field(default_factory=list)

    def get_context_string(self, max_files: int = 5, max_chars: int = 4000) -> str:
        """Format matches for prompt injection."""
        if not self.matches:
            return ""

        lines = ["## Relevant Files\n"]
        char_count = 0

        # Sort by relevance
        sorted_matches = sorted(self.matches, key=lambda m: -m.relevance)

        for match in sorted_matches[:max_files]:
            entry = f"**{match.path}** ({match.match_reason})"
            if match.preview:
                entry += f"\n```\n{match.preview}\n```"

            if char_count + len(entry) > max_chars:
                break

            lines.append(entry)
            char_count += len(entry)

        return "\n\n".join(lines)


class SmartContextLoader:
    """Automatically finds relevant files based on task description."""

    # Patterns to extract from prompts
    FILE_PATTERN = re.compile(r'[\w\-]+\.(?:py|js|ts|jsx|tsx|go|rs|java|rb|php|vue|svelte|css|scss|html|json|yaml|yml|toml|md)')
    FUNC_PATTERN = re.compile(r'\b(?:function|def|fn|func)\s+(\w+)|(\w+)\s*\(')
    CLASS_PATTERN = re.compile(r'\b(?:class|struct|interface|type)\s+(\w+)')
    IMPORT_PATTERN = re.compile(r'(?:from|import)\s+([\w\.]+)')

    # Common code keywords that suggest file types
    KEYWORD_MAP = {
        'auth': ['auth', 'login', 'user', 'session', 'token'],
        'api': ['api', 'endpoint', 'route', 'handler', 'controller'],
        'database': ['db', 'database', 'model', 'schema', 'migration'],
        'test': ['test', 'spec', 'mock'],
        'config': ['config', 'settings', 'env'],
        'ui': ['component', 'view', 'page', 'template'],
    }

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = project_dir or Path.cwd()
        self._file_cache: dict[str, list[Path]] | None = None

    def load(self, prompt: str, max_files: int = 5) -> SmartContext:
        """Load relevant context based on prompt.

        Args:
            prompt: The user's task description
            max_files: Maximum number of files to include

        Returns:
            SmartContext with matched files
        """
        context = SmartContext()

        # Extract keywords and patterns from prompt
        prompt_lower = prompt.lower()

        # 1. Direct file references
        file_refs = self.FILE_PATTERN.findall(prompt)
        for ref in file_refs:
            matches = self._find_files(ref)
            for path in matches[:2]:  # Limit per reference
                context.matches.append(ContextMatch(
                    path=path,
                    relevance=1.0,
                    match_reason=f"directly mentioned",
                    preview=self._get_preview(path),
                ))
                context.keywords_found.append(ref)

        # 2. Function/class names
        func_matches = self.FUNC_PATTERN.findall(prompt)
        funcs = [m[0] or m[1] for m in func_matches if m[0] or m[1]]
        for func in funcs:
            if len(func) < 3 or func in ('the', 'and', 'for', 'def', 'class'):
                continue
            matches = self._grep_files(func)
            for path in matches[:2]:
                if not self._already_matched(context, path):
                    context.matches.append(ContextMatch(
                        path=path,
                        relevance=0.8,
                        match_reason=f"contains '{func}'",
                        preview=self._get_preview(path, func),
                    ))

        class_matches = self.CLASS_PATTERN.findall(prompt)
        for cls in class_matches:
            matches = self._grep_files(f"class {cls}")
            for path in matches[:2]:
                if not self._already_matched(context, path):
                    context.matches.append(ContextMatch(
                        path=path,
                        relevance=0.9,
                        match_reason=f"defines '{cls}'",
                        preview=self._get_preview(path, cls),
                    ))

        # 3. Import paths
        import_matches = self.IMPORT_PATTERN.findall(prompt)
        for imp in import_matches:
            # Convert import to file path
            imp_path = imp.replace('.', '/') + '.py'
            matches = self._find_files(imp_path)
            for path in matches[:1]:
                if not self._already_matched(context, path):
                    context.matches.append(ContextMatch(
                        path=path,
                        relevance=0.85,
                        match_reason=f"import reference",
                        preview=self._get_preview(path),
                    ))

        # 4. Keyword-based discovery
        for category, keywords in self.KEYWORD_MAP.items():
            if any(kw in prompt_lower for kw in keywords):
                context.keywords_found.append(category)
                # Search for files with these keywords
                for kw in keywords:
                    if kw in prompt_lower:
                        matches = self._find_files(f"*{kw}*")
                        for path in matches[:2]:
                            if not self._already_matched(context, path):
                                context.matches.append(ContextMatch(
                                    path=path,
                                    relevance=0.6,
                                    match_reason=f"matches '{category}' context",
                                    preview=self._get_preview(path),
                                ))
                        break

        # Limit total matches
        context.matches = sorted(context.matches, key=lambda m: -m.relevance)[:max_files]

        return context

    def _find_files(self, pattern: str) -> list[Path]:
        """Find files matching pattern using glob."""
        try:
            # Try exact match first
            if '*' not in pattern:
                exact = list(self.project_dir.rglob(pattern))
                if exact:
                    return [p for p in exact if self._is_valid_file(p)]

            # Then glob
            matches = list(self.project_dir.rglob(f"**/{pattern}"))
            return [p for p in matches if self._is_valid_file(p)][:10]
        except Exception:
            return []

    def _grep_files(self, pattern: str) -> list[Path]:
        """Search file contents for pattern using grep/rg."""
        try:
            # Try ripgrep first (faster)
            result = subprocess.run(
                ['rg', '-l', '--type-not', 'binary', '-g', '!node_modules', '-g', '!.git', '-g', '!*.lock', pattern],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                paths = [self.project_dir / p for p in result.stdout.strip().split('\n') if p]
                return [p for p in paths if self._is_valid_file(p)][:10]
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # Fallback to grep
        try:
            result = subprocess.run(
                ['grep', '-rl', '--include=*.py', '--include=*.js', '--include=*.ts', pattern, '.'],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                paths = [self.project_dir / p.lstrip('./') for p in result.stdout.strip().split('\n') if p]
                return [p for p in paths if self._is_valid_file(p)][:10]
        except Exception:
            pass

        return []

    def _is_valid_file(self, path: Path) -> bool:
        """Check if path is a valid source file."""
        if not path.is_file():
            return False

        # Skip common non-source paths
        skip_patterns = ['node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build', '.egg']
        path_str = str(path)
        if any(skip in path_str for skip in skip_patterns):
            return False

        # Check extension
        valid_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java', '.rb', '.vue', '.svelte'}
        return path.suffix in valid_extensions

    def _get_preview(self, path: Path, highlight: str | None = None, max_lines: int = 10) -> str:
        """Get a preview of the file content."""
        try:
            content = path.read_text()
            lines = content.split('\n')

            if highlight:
                # Find the section containing the highlight
                for i, line in enumerate(lines):
                    if highlight.lower() in line.lower():
                        start = max(0, i - 2)
                        end = min(len(lines), i + max_lines - 2)
                        return '\n'.join(lines[start:end])

            # Return first N lines
            return '\n'.join(lines[:max_lines])
        except Exception:
            return ""

    def _already_matched(self, context: SmartContext, path: Path) -> bool:
        """Check if path is already in matches."""
        return any(m.path == path for m in context.matches)


def load_smart_context(prompt: str, project_dir: Path | None = None) -> SmartContext:
    """Convenience function to load smart context."""
    loader = SmartContextLoader(project_dir)
    return loader.load(prompt)
