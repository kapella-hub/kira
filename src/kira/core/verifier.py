"""Verification layer for validating execution results."""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import KiraClient


class CheckType(Enum):
    """Types of verification checks."""

    SYNTAX = "syntax"
    IMPORTS = "imports"
    TYPES = "types"
    TESTS = "tests"
    COMPLETION = "completion"
    CUSTOM = "custom"


class CheckStatus(Enum):
    """Status of a verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class VerificationCheck:
    """Result of a single verification check."""

    check_type: CheckType
    status: CheckStatus
    message: str
    details: str = ""
    file_path: str | None = None
    line_number: int | None = None

    def to_context(self) -> str:
        """Format check for display."""
        status_symbol = {
            CheckStatus.PASSED: "[green]PASS[/green]",
            CheckStatus.FAILED: "[red]FAIL[/red]",
            CheckStatus.SKIPPED: "[dim]SKIP[/dim]",
            CheckStatus.WARNING: "[yellow]WARN[/yellow]",
        }.get(self.status, "???")

        parts = [f"{status_symbol} {self.check_type.value}: {self.message}"]
        if self.file_path:
            loc = self.file_path
            if self.line_number:
                loc += f":{self.line_number}"
            parts.append(f"  at {loc}")
        if self.details:
            parts.append(f"  {self.details}")
        return "\n".join(parts)


@dataclass
class VerificationResult:
    """Aggregate result of all verification checks."""

    checks: list[VerificationCheck] = field(default_factory=list)
    overall_passed: bool = True

    @property
    def passed_count(self) -> int:
        """Number of passed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.PASSED)

    @property
    def failed_count(self) -> int:
        """Number of failed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FAILED)

    @property
    def issues(self) -> list[str]:
        """List of issue messages from failed checks."""
        return [c.message for c in self.checks if c.status == CheckStatus.FAILED]

    def to_context(self) -> str:
        """Format result for display."""
        lines = [
            f"Verification: {self.passed_count}/{len(self.checks)} checks passed",
            "",
        ]
        for check in self.checks:
            lines.append(check.to_context())
        return "\n".join(lines)


class Verifier:
    """Verifies execution results before declaring success."""

    def __init__(
        self,
        client: KiraClient | None = None,
        working_dir: Path | None = None,
    ):
        """Initialize verifier.

        Args:
            client: Optional KiraClient for LLM-based verification.
            working_dir: Working directory for file operations.
        """
        self.client = client
        self.working_dir = working_dir or Path.cwd()

    async def verify(
        self,
        task: str,
        output: str,
        files_modified: list[str] | None = None,
        run_tests: bool = True,
        check_types: bool = False,
    ) -> VerificationResult:
        """Run all verification checks.

        Args:
            task: Original task description.
            output: Execution output to verify.
            files_modified: List of files that were modified.
            run_tests: Whether to run tests.
            check_types: Whether to run type checking.

        Returns:
            Verification result with all checks.
        """
        checks: list[VerificationCheck] = []
        files = files_modified or []

        # 1. Check syntax for Python files
        for file_path in files:
            if file_path.endswith(".py"):
                check = self._check_syntax(file_path)
                checks.append(check)

        # 2. Check imports resolve
        for file_path in files:
            if file_path.endswith(".py"):
                check = self._check_imports(file_path)
                checks.append(check)

        # 3. Optional: Run type checker
        if check_types and files:
            py_files = [f for f in files if f.endswith(".py")]
            if py_files:
                check = self._check_types(py_files)
                checks.append(check)

        # 4. Optional: Run tests
        if run_tests:
            check = await self._check_tests()
            checks.append(check)

        # 5. LLM judge: task completion
        if self.client:
            check = await self._check_completion(task, output, files)
            checks.append(check)

        # Determine overall result
        overall_passed = all(
            c.status in (CheckStatus.PASSED, CheckStatus.SKIPPED, CheckStatus.WARNING)
            for c in checks
        )

        return VerificationResult(checks=checks, overall_passed=overall_passed)

    def _check_syntax(self, file_path: str) -> VerificationCheck:
        """Check Python syntax.

        Args:
            file_path: Path to Python file.

        Returns:
            Verification check result.
        """
        full_path = self.working_dir / file_path
        if not full_path.exists():
            return VerificationCheck(
                check_type=CheckType.SYNTAX,
                status=CheckStatus.SKIPPED,
                message=f"File not found: {file_path}",
                file_path=file_path,
            )

        try:
            source = full_path.read_text()
            ast.parse(source)
            return VerificationCheck(
                check_type=CheckType.SYNTAX,
                status=CheckStatus.PASSED,
                message="Syntax valid",
                file_path=file_path,
            )
        except SyntaxError as e:
            return VerificationCheck(
                check_type=CheckType.SYNTAX,
                status=CheckStatus.FAILED,
                message=f"Syntax error: {e.msg}",
                details=str(e),
                file_path=file_path,
                line_number=e.lineno,
            )

    def _check_imports(self, file_path: str) -> VerificationCheck:
        """Check that imports are valid.

        Args:
            file_path: Path to Python file.

        Returns:
            Verification check result.
        """
        full_path = self.working_dir / file_path
        if not full_path.exists():
            return VerificationCheck(
                check_type=CheckType.IMPORTS,
                status=CheckStatus.SKIPPED,
                message=f"File not found: {file_path}",
                file_path=file_path,
            )

        try:
            source = full_path.read_text()
            tree = ast.parse(source)
        except SyntaxError:
            return VerificationCheck(
                check_type=CheckType.IMPORTS,
                status=CheckStatus.SKIPPED,
                message="Cannot check imports due to syntax error",
                file_path=file_path,
            )

        # Extract import statements
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])

        # Check each import
        missing: list[str] = []
        for module in set(imports):
            # Skip relative imports and builtins
            if module.startswith(".") or module in sys.builtin_module_names:
                continue
            # Skip local imports (assume they exist)
            if (self.working_dir / module).exists() or (self.working_dir / f"{module}.py").exists():
                continue

            # Try to import
            try:
                __import__(module)
            except ImportError:
                missing.append(module)

        if missing:
            return VerificationCheck(
                check_type=CheckType.IMPORTS,
                status=CheckStatus.WARNING,
                message=f"Potentially missing imports: {', '.join(missing)}",
                details="These modules may need to be installed",
                file_path=file_path,
            )

        return VerificationCheck(
            check_type=CheckType.IMPORTS,
            status=CheckStatus.PASSED,
            message="All imports valid",
            file_path=file_path,
        )

    def _check_types(self, files: list[str]) -> VerificationCheck:
        """Run type checker on files.

        Args:
            files: List of Python files to check.

        Returns:
            Verification check result.
        """
        # Try mypy first, fall back to pyright
        for checker in ["mypy", "pyright"]:
            try:
                result = subprocess.run(
                    [checker] + files,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return VerificationCheck(
                        check_type=CheckType.TYPES,
                        status=CheckStatus.PASSED,
                        message=f"Type check passed ({checker})",
                    )
                else:
                    return VerificationCheck(
                        check_type=CheckType.TYPES,
                        status=CheckStatus.WARNING,
                        message=f"Type errors found ({checker})",
                        details=result.stdout[:500] if result.stdout else result.stderr[:500],
                    )
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return VerificationCheck(
                    check_type=CheckType.TYPES,
                    status=CheckStatus.SKIPPED,
                    message="Type check timed out",
                )

        return VerificationCheck(
            check_type=CheckType.TYPES,
            status=CheckStatus.SKIPPED,
            message="No type checker available (mypy/pyright)",
        )

    async def _check_tests(self) -> VerificationCheck:
        """Run project tests.

        Returns:
            Verification check result.
        """
        # Detect test runner
        runners = [
            (["pytest", "--tb=short", "-q"], "pytest"),
            (["python", "-m", "unittest", "discover"], "unittest"),
        ]

        for cmd, name in runners:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return VerificationCheck(
                        check_type=CheckType.TESTS,
                        status=CheckStatus.PASSED,
                        message=f"Tests passed ({name})",
                        details=self._extract_test_summary(result.stdout),
                    )
                else:
                    return VerificationCheck(
                        check_type=CheckType.TESTS,
                        status=CheckStatus.FAILED,
                        message=f"Tests failed ({name})",
                        details=result.stdout[-500:] if result.stdout else result.stderr[-500:],
                    )
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return VerificationCheck(
                    check_type=CheckType.TESTS,
                    status=CheckStatus.WARNING,
                    message="Tests timed out",
                )

        return VerificationCheck(
            check_type=CheckType.TESTS,
            status=CheckStatus.SKIPPED,
            message="No test runner available",
        )

    def _extract_test_summary(self, output: str) -> str:
        """Extract test summary from output."""
        lines = output.strip().split("\n")
        # Look for summary line (usually last few lines)
        for line in reversed(lines[-5:]):
            if "passed" in line.lower() or "failed" in line.lower():
                return line.strip()
        return ""

    async def _check_completion(
        self, task: str, output: str, files: list[str]
    ) -> VerificationCheck:
        """Use LLM to judge if task was completed.

        Args:
            task: Original task description.
            output: Execution output.
            files: Files that were modified.

        Returns:
            Verification check result.
        """
        if not self.client:
            return VerificationCheck(
                check_type=CheckType.COMPLETION,
                status=CheckStatus.SKIPPED,
                message="No client for completion check",
            )

        prompt = f"""Evaluate if this task was completed successfully.

TASK: {task}

EXECUTION OUTPUT:
{output[:2000]}

FILES MODIFIED: {", ".join(files) if files else "None specified"}

Respond with:
[COMPLETED:yes/no/partial]
[CONFIDENCE:0.0-1.0]
[REASON:brief explanation]
"""

        output_parts: list[str] = []
        async for chunk in self.client.run(prompt):
            output_parts.append(chunk)
        response = "".join(output_parts)

        # Parse response
        completed = "yes" in response.lower()
        partial = "partial" in response.lower()

        if completed:
            return VerificationCheck(
                check_type=CheckType.COMPLETION,
                status=CheckStatus.PASSED,
                message="Task appears complete",
                details=response,
            )
        elif partial:
            return VerificationCheck(
                check_type=CheckType.COMPLETION,
                status=CheckStatus.WARNING,
                message="Task partially complete",
                details=response,
            )
        else:
            return VerificationCheck(
                check_type=CheckType.COMPLETION,
                status=CheckStatus.FAILED,
                message="Task may not be complete",
                details=response,
            )

    def verify_file_syntax(self, file_path: str) -> bool:
        """Quick syntax check for a file.

        Args:
            file_path: Path to file.

        Returns:
            True if syntax is valid.
        """
        check = self._check_syntax(file_path)
        return check.status == CheckStatus.PASSED
