"""Failure analysis for self-correction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import (
    CorrectionStrategy,
    ExecutionAttempt,
    FailureAnalysis,
    FailureType,
)

if TYPE_CHECKING:
    from ..core.client import KiraClient


# Patterns for detecting failure types
FAILURE_PATTERNS: dict[FailureType, list[re.Pattern[str]]] = {
    FailureType.SYNTAX_ERROR: [
        re.compile(r"SyntaxError:", re.IGNORECASE),
        re.compile(r"IndentationError:", re.IGNORECASE),
        re.compile(r"invalid syntax", re.IGNORECASE),
        re.compile(r"unexpected token", re.IGNORECASE),
    ],
    FailureType.IMPORT_ERROR: [
        re.compile(r"ImportError:", re.IGNORECASE),
        re.compile(r"ModuleNotFoundError:", re.IGNORECASE),
        re.compile(r"No module named", re.IGNORECASE),
        re.compile(r"cannot find module", re.IGNORECASE),
    ],
    FailureType.TYPE_ERROR: [
        re.compile(r"TypeError:", re.IGNORECASE),
        re.compile(r"type.*mismatch", re.IGNORECASE),
        re.compile(r"expected.*got", re.IGNORECASE),
    ],
    FailureType.RUNTIME_ERROR: [
        re.compile(r"RuntimeError:", re.IGNORECASE),
        re.compile(r"Exception:", re.IGNORECASE),
        re.compile(r"Error:", re.IGNORECASE),
        re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    ],
    FailureType.TEST_FAILURE: [
        re.compile(r"FAILED", re.IGNORECASE),
        re.compile(r"AssertionError:", re.IGNORECASE),
        re.compile(r"test.*failed", re.IGNORECASE),
        re.compile(r"\d+ failed", re.IGNORECASE),
    ],
    FailureType.TIMEOUT: [
        re.compile(r"timeout", re.IGNORECASE),
        re.compile(r"timed out", re.IGNORECASE),
        re.compile(r"deadline exceeded", re.IGNORECASE),
    ],
}


class FailureAnalyzer:
    """Analyzes execution failures to determine root cause and correction strategy."""

    def __init__(self, client: KiraClient | None = None):
        """Initialize analyzer.

        Args:
            client: Optional KiraClient for LLM-based analysis.
        """
        self.client = client

    def detect_failure_type(self, error: str, result: str) -> FailureType:
        """Detect failure type from error message and result.

        Args:
            error: Error message if any.
            result: Execution result/output.

        Returns:
            Detected failure type.
        """
        text = f"{error or ''} {result or ''}"

        # Check patterns in priority order
        priority_order = [
            FailureType.SYNTAX_ERROR,
            FailureType.IMPORT_ERROR,
            FailureType.TYPE_ERROR,
            FailureType.TEST_FAILURE,
            FailureType.TIMEOUT,
            FailureType.RUNTIME_ERROR,
        ]

        for failure_type in priority_order:
            patterns = FAILURE_PATTERNS.get(failure_type, [])
            for pattern in patterns:
                if pattern.search(text):
                    return failure_type

        return FailureType.UNKNOWN

    def get_strategy_for_failure(
        self, failure_type: FailureType, attempt_count: int
    ) -> CorrectionStrategy:
        """Determine correction strategy based on failure type and attempt count.

        Args:
            failure_type: Type of failure encountered.
            attempt_count: Number of attempts so far.

        Returns:
            Recommended correction strategy.
        """
        # After multiple failures, try more drastic measures
        if attempt_count >= 3:
            return CorrectionStrategy.ALTERNATIVE_APPROACH
        if attempt_count >= 2:
            return CorrectionStrategy.SIMPLIFY

        # Strategy based on failure type
        strategy_map = {
            FailureType.SYNTAX_ERROR: CorrectionStrategy.RETRY_SAME,  # Just fix syntax
            FailureType.IMPORT_ERROR: CorrectionStrategy.MODIFY_APPROACH,  # Fix imports
            FailureType.TYPE_ERROR: CorrectionStrategy.MODIFY_APPROACH,
            FailureType.TEST_FAILURE: CorrectionStrategy.MODIFY_APPROACH,
            FailureType.RUNTIME_ERROR: CorrectionStrategy.MODIFY_APPROACH,
            FailureType.LOGIC_ERROR: CorrectionStrategy.ALTERNATIVE_APPROACH,
            FailureType.INCOMPLETE: CorrectionStrategy.SIMPLIFY,
            FailureType.TIMEOUT: CorrectionStrategy.SIMPLIFY,
            FailureType.UNKNOWN: CorrectionStrategy.MODIFY_APPROACH,
        }

        return strategy_map.get(failure_type, CorrectionStrategy.MODIFY_APPROACH)

    def analyze_quick(self, attempt: ExecutionAttempt) -> FailureAnalysis:
        """Quick pattern-based failure analysis (no LLM call).

        Args:
            attempt: The failed execution attempt.

        Returns:
            Analysis of the failure.
        """
        failure_type = self.detect_failure_type(
            attempt.error or "", attempt.result
        )
        strategy = self.get_strategy_for_failure(
            failure_type, attempt.attempt_number
        )

        # Generate basic root cause
        root_cause = self._infer_root_cause(failure_type, attempt)
        suggested_fixes = self._suggest_fixes(failure_type, attempt)

        return FailureAnalysis(
            failure_type=failure_type,
            root_cause=root_cause,
            contributing_factors=[],
            suggested_fixes=suggested_fixes,
            recommended_strategy=strategy,
            confidence=0.6,  # Lower confidence for quick analysis
        )

    async def analyze_deep(
        self,
        attempt: ExecutionAttempt,
        task: str,
        previous_attempts: list[ExecutionAttempt] | None = None,
    ) -> FailureAnalysis:
        """Deep LLM-based failure analysis.

        Args:
            attempt: The failed execution attempt.
            task: Original task description.
            previous_attempts: Previous failed attempts for context.

        Returns:
            Detailed analysis of the failure.
        """
        if not self.client:
            return self.analyze_quick(attempt)

        # Build context from previous attempts
        attempts_context = ""
        if previous_attempts:
            attempts_context = "\n\n".join(
                a.to_context() for a in previous_attempts
            )

        prompt = f"""Analyze this execution failure and provide structured analysis.

TASK: {task}

CURRENT ATTEMPT:
{attempt.to_context()}

{f"PREVIOUS ATTEMPTS:{chr(10)}{attempts_context}" if attempts_context else ""}

Analyze the failure and respond with:

[FAILURE_TYPE:value]
One of: syntax_error, runtime_error, test_failure, import_error, type_error, logic_error, incomplete, timeout, unknown

[ROOT_CAUSE:text]
The primary reason for the failure.

[CONTRIBUTING_FACTORS:item1|item2|item3]
Other factors that contributed to the failure.

[SUGGESTED_FIXES:fix1|fix2|fix3]
Specific fixes to try.

[STRATEGY:value]
One of: retry_same, modify_approach, alternative_approach, simplify, seek_help

[CONFIDENCE:0.0-1.0]
How confident you are in this analysis.
"""

        # Run analysis
        output_parts: list[str] = []
        async for chunk in self.client.run(prompt):
            output_parts.append(chunk)
        raw_output = "".join(output_parts)

        # Parse response
        return self._parse_analysis(raw_output, attempt)

    def _infer_root_cause(
        self, failure_type: FailureType, attempt: ExecutionAttempt
    ) -> str:
        """Infer root cause from failure type and attempt data."""
        error = attempt.error or attempt.result or ""

        cause_templates = {
            FailureType.SYNTAX_ERROR: "Code contains syntax error",
            FailureType.IMPORT_ERROR: "Missing or incorrect import statement",
            FailureType.TYPE_ERROR: "Type mismatch in function call or assignment",
            FailureType.TEST_FAILURE: "Implementation does not match expected behavior",
            FailureType.RUNTIME_ERROR: "Runtime exception during execution",
            FailureType.LOGIC_ERROR: "Logic error in implementation",
            FailureType.INCOMPLETE: "Implementation is incomplete",
            FailureType.TIMEOUT: "Execution exceeded time limit",
            FailureType.UNKNOWN: "Unknown error occurred",
        }

        base_cause = cause_templates.get(failure_type, "Unknown error")

        # Try to extract more specific info from error
        if "line" in error.lower():
            # Extract line number if present
            line_match = re.search(r"line (\d+)", error, re.IGNORECASE)
            if line_match:
                base_cause += f" at line {line_match.group(1)}"

        return base_cause

    def _suggest_fixes(
        self, failure_type: FailureType, attempt: ExecutionAttempt
    ) -> list[str]:
        """Suggest fixes based on failure type."""
        error = attempt.error or attempt.result or ""

        fixes_map: dict[FailureType, list[str]] = {
            FailureType.SYNTAX_ERROR: [
                "Check for missing colons, parentheses, or brackets",
                "Verify indentation is consistent",
                "Look for typos in keywords",
            ],
            FailureType.IMPORT_ERROR: [
                "Verify module is installed",
                "Check import path is correct",
                "Try relative vs absolute import",
            ],
            FailureType.TYPE_ERROR: [
                "Check argument types match function signature",
                "Verify return type is correct",
                "Add type conversions if needed",
            ],
            FailureType.TEST_FAILURE: [
                "Review test expectations",
                "Check edge cases",
                "Verify implementation logic",
            ],
            FailureType.RUNTIME_ERROR: [
                "Add error handling",
                "Check for None/null values",
                "Verify data is in expected format",
            ],
            FailureType.TIMEOUT: [
                "Optimize algorithm complexity",
                "Add early termination conditions",
                "Break into smaller operations",
            ],
        }

        # Get base fixes
        fixes = fixes_map.get(failure_type, ["Review error message and fix"])

        # Add specific fixes based on error content
        if "not defined" in error.lower():
            fixes.insert(0, "Define the missing variable or function")
        if "permission" in error.lower():
            fixes.insert(0, "Check file/directory permissions")
        if "memory" in error.lower():
            fixes.insert(0, "Reduce memory usage or batch operations")

        return fixes[:3]  # Return top 3 suggestions

    def _parse_analysis(
        self, raw_output: str, attempt: ExecutionAttempt
    ) -> FailureAnalysis:
        """Parse LLM analysis output."""
        # Extract fields using markers
        failure_type_match = re.search(
            r"\[FAILURE_TYPE:([^\]]+)\]", raw_output
        )
        root_cause_match = re.search(r"\[ROOT_CAUSE:([^\]]+)\]", raw_output)
        factors_match = re.search(
            r"\[CONTRIBUTING_FACTORS:([^\]]+)\]", raw_output
        )
        fixes_match = re.search(r"\[SUGGESTED_FIXES:([^\]]+)\]", raw_output)
        strategy_match = re.search(r"\[STRATEGY:([^\]]+)\]", raw_output)
        confidence_match = re.search(r"\[CONFIDENCE:([^\]]+)\]", raw_output)

        # Parse failure type
        failure_type = FailureType.UNKNOWN
        if failure_type_match:
            try:
                failure_type = FailureType(failure_type_match.group(1).strip())
            except ValueError:
                failure_type = self.detect_failure_type(
                    attempt.error or "", attempt.result
                )

        # Parse strategy
        strategy = CorrectionStrategy.MODIFY_APPROACH
        if strategy_match:
            try:
                strategy = CorrectionStrategy(strategy_match.group(1).strip())
            except ValueError:
                pass

        # Parse confidence
        confidence = 0.7
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1).strip())
            except ValueError:
                pass

        return FailureAnalysis(
            failure_type=failure_type,
            root_cause=(
                root_cause_match.group(1).strip()
                if root_cause_match
                else self._infer_root_cause(failure_type, attempt)
            ),
            contributing_factors=(
                [f.strip() for f in factors_match.group(1).split("|")]
                if factors_match
                else []
            ),
            suggested_fixes=(
                [f.strip() for f in fixes_match.group(1).split("|")]
                if fixes_match
                else self._suggest_fixes(failure_type, attempt)
            ),
            recommended_strategy=strategy,
            confidence=confidence,
            raw_output=raw_output,
        )
