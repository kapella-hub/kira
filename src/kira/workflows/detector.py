"""CodingTaskDetector - Aggressively detect coding tasks for workflow routing."""

from __future__ import annotations

import re


class CodingTaskDetector:
    """Aggressively detect coding tasks for workflow routing.

    Uses regex patterns to identify coding-related tasks
    with high confidence.
    """

    # Strong indicators - high confidence
    STRONG_PATTERNS = [
        # Action + target combinations
        r"\b(implement|create|build|develop|write|add)\b.*\b(feature|function|class|method|endpoint|api|module)\b",
        r"\b(add|create|implement)\b.*\b(to|for|in)\b.*\.(py|js|ts|go|rs|java|rb|php)\b",
        r"\brefactor\b.*\b(code|function|class|module)\b",
        r"\b(make|build)\s+(a|an|the)\s+\w+\s+(app|application|service|tool|script)\b",
        # Implement with common coding targets
        r"\b(implement|create|build|add)\b.*\b(auth|authentication|login|logout|signup|register)\b",
        r"\b(implement|create|build|add)\b.*\b(payment|checkout|billing|subscription)\b",
        r"\b(implement|create|build|add)\b.*\b(crud|rest|graphql|websocket)\b",
        r"\b(implement|create|build|add)\b.*\b(validation|middleware|decorator)\b",
        # Fix/update patterns
        r"\b(fix|update|modify|change)\b.*\b(bug|issue|error|code)\b",
    ]

    # Moderate indicators
    MODERATE_PATTERNS = [
        r"\bcan you\b.*\b(make|create|write|build|implement)\b",
        r"\bneed to\b.*\b(implement|add|create|build)\b",
        r"\bhow (do|would|can) (i|we|you)\b.*\b(implement|create|build)\b",
        r"\b(write|create)\b.*\b(test|tests)\b",
        # Standalone action verbs (less confident but still indicator)
        r"^(implement|create|build|develop|write|add|code)\b",
    ]

    # Context clues - boost confidence
    CONTEXT_CLUES = [
        "file",
        "function",
        "class",
        "method",
        "module",
        "api",
        "endpoint",
        "database",
        "model",
        "test",
        "component",
        "service",
        "handler",
        "controller",
        "route",
        "schema",
        # Additional coding-related terms
        "auth",
        "authentication",
        "login",
        "user",
        "payment",
        "feature",
        "crud",
        "rest",
        "validation",
    ]

    # Negative indicators - reduce confidence
    NEGATIVE_PATTERNS = [
        r"\bexplain\b",
        r"\bwhat is\b",
        r"\bhow does\b",
        r"\bwhy\b",
        r"\bdescribe\b",
        r"\blist\b",
        r"\bshow me\b",
    ]

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def is_coding_task(self, prompt: str) -> tuple[bool, float]:
        """Determine if prompt is a coding task.

        Args:
            prompt: The user's prompt

        Returns:
            (is_coding, confidence_score)
        """
        prompt_lower = prompt.lower()
        confidence = 0.0

        # Check negative patterns first
        for pattern in self.NEGATIVE_PATTERNS:
            if re.search(pattern, prompt_lower):
                confidence -= 0.3

        # Check strong patterns
        for pattern in self.STRONG_PATTERNS:
            if re.search(pattern, prompt_lower):
                confidence += 0.5

        # Check moderate patterns
        for pattern in self.MODERATE_PATTERNS:
            if re.search(pattern, prompt_lower):
                confidence += 0.25

        # Check context clues
        clue_count = sum(1 for clue in self.CONTEXT_CLUES if clue in prompt_lower)
        confidence += min(clue_count * 0.1, 0.3)

        # Clamp to [0, 1]
        confidence = max(0.0, min(confidence, 1.0))

        return confidence >= self.threshold, confidence

    def get_recommended_workflow(self, prompt: str) -> str | None:
        """Get the recommended workflow for a prompt.

        Args:
            prompt: The user's prompt

        Returns:
            Workflow name or None
        """
        is_coding, confidence = self.is_coding_task(prompt)

        if not is_coding:
            return None

        # Check for quick/fast keywords
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ["quick", "fast", "simple", "just"]):
            return "quick-coding"

        return "coding"
