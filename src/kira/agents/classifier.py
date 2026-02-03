"""TaskClassifier - Classify tasks to determine appropriate agents."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import ClassifiedTask, TaskType

if TYPE_CHECKING:
    from ..core.client import KiraClient


class TaskClassifier:
    """Classify tasks to determine appropriate agents.

    Uses keyword-based fast classification first,
    then optionally LLM classification for ambiguous cases.
    """

    # Keyword patterns for fast classification
    KEYWORD_PATTERNS: dict[TaskType, list[str]] = {
        TaskType.CODING: [
            "implement",
            "create",
            "add feature",
            "build",
            "write code",
            "develop",
            "code",
            "function",
            "class",
            "method",
        ],
        TaskType.DEBUGGING: [
            "fix",
            "debug",
            "error",
            "bug",
            "not working",
            "fails",
            "broken",
            "issue",
            "problem",
        ],
        TaskType.ARCHITECTURE: [
            "design",
            "architect",
            "structure",
            "plan",
            "system",
            "how should",
            "approach",
        ],
        TaskType.DOCUMENTATION: [
            "document",
            "readme",
            "comment",
            "explain code",
            "docstring",
            "docs",
        ],
        TaskType.RESEARCH: [
            "research",
            "investigate",
            "compare",
            "evaluate",
            "options",
            "what is",
            "how does",
        ],
        TaskType.REVIEW: [
            "review",
            "check",
            "audit",
            "assess",
            "feedback",
        ],
    }

    # Default agents for each task type
    DEFAULT_AGENTS: dict[TaskType, list[str]] = {
        TaskType.CODING: ["coder"],
        TaskType.ARCHITECTURE: ["architect"],
        TaskType.DEBUGGING: ["debugger", "coder"],
        TaskType.DOCUMENTATION: ["documenter"],
        TaskType.RESEARCH: ["researcher"],
        TaskType.REVIEW: ["reviewer"],
        TaskType.GENERAL: ["orchestrator"],
    }

    # LLM classification prompt
    CLASSIFICATION_PROMPT = """Classify this task and recommend appropriate handling.

Task types:
- coding: Implement new features, write code
- architecture: Design systems, plan structure
- debugging: Fix bugs, troubleshoot issues
- documentation: Write/update docs, comments
- research: Investigate options, gather information
- review: Code review, quality assessment
- general: Other tasks

Output format:
[CLASSIFY:type] task_type
[CLASSIFY:complexity] simple OR moderate OR complex
[CLASSIFY:agents] comma,separated,agent,names
[CLASSIFY:reasoning] Brief explanation

Task to classify:
"""

    def __init__(self, kiro_client: KiraClient | None = None):
        self.client = kiro_client

    def quick_classify(self, prompt: str) -> tuple[TaskType | None, float]:
        """Fast keyword-based classification (no LLM call).

        Returns (task_type, confidence) or (None, 0) if no match.
        """
        prompt_lower = prompt.lower()
        best_match: TaskType | None = None
        best_score = 0.0

        for task_type, keywords in self.KEYWORD_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in prompt_lower)
            if score > best_score:
                best_score = score
                best_match = task_type

        # Normalize confidence
        confidence = min(best_score / 3, 1.0) if best_score > 0 else 0.0
        return best_match, confidence

    async def classify(
        self,
        prompt: str,
        use_llm: bool = False,
    ) -> ClassifiedTask:
        """Classify task and recommend agents.

        Args:
            prompt: The task/prompt to classify
            use_llm: Whether to use LLM for classification (slower but more accurate)

        Returns:
            ClassifiedTask with type, complexity, and recommended agents
        """
        # Try quick classification first
        quick_type, confidence = self.quick_classify(prompt)

        if quick_type and (confidence >= 0.5 or not use_llm):
            return ClassifiedTask(
                original_prompt=prompt,
                task_type=quick_type,
                complexity="moderate",
                recommended_agents=self.DEFAULT_AGENTS.get(quick_type, ["orchestrator"]),
                confidence=confidence,
                reasoning="Keyword-based classification",
            )

        # Use LLM classification if available and requested
        if use_llm and self.client:
            return await self._llm_classify(prompt)

        # Fallback to general
        return ClassifiedTask(
            original_prompt=prompt,
            task_type=TaskType.GENERAL,
            complexity="moderate",
            recommended_agents=["orchestrator"],
            confidence=0.3,
            reasoning="Default classification",
        )

    async def _llm_classify(self, prompt: str) -> ClassifiedTask:
        """Use LLM for classification."""
        if not self.client:
            raise ValueError("KiraClient required for LLM classification")

        result = await self.client.run_batch(f"{self.CLASSIFICATION_PROMPT}\n{prompt}")
        return self._parse_classification(prompt, result.output)

    def _parse_classification(self, prompt: str, output: str) -> ClassifiedTask:
        """Parse LLM classification output."""
        # Extract type
        type_match = re.search(r"\[CLASSIFY:type\]\s*(\w+)", output, re.IGNORECASE)
        task_type = TaskType.GENERAL
        if type_match:
            task_type = TaskType.from_string(type_match.group(1))

        # Extract complexity
        complexity_match = re.search(r"\[CLASSIFY:complexity\]\s*(\w+)", output, re.IGNORECASE)
        complexity = complexity_match.group(1).strip() if complexity_match else "moderate"

        # Extract agents
        agents_match = re.search(r"\[CLASSIFY:agents\]\s*(.+?)(?=\[|$)", output, re.IGNORECASE)
        agents = self.DEFAULT_AGENTS.get(task_type, ["orchestrator"])
        if agents_match:
            agents = [a.strip() for a in agents_match.group(1).split(",") if a.strip()]

        # Extract reasoning
        reasoning_match = re.search(
            r"\[CLASSIFY:reasoning\]\s*(.+?)(?=\[|$)", output, re.IGNORECASE | re.DOTALL
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "LLM classification"

        return ClassifiedTask(
            original_prompt=prompt,
            task_type=task_type,
            complexity=complexity,
            recommended_agents=agents,
            confidence=0.8,
            reasoning=reasoning,
        )
