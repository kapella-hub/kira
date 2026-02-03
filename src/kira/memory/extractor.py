"""Auto-extraction of memories from LLM responses.

Extracts potential memories from text without requiring explicit markers.
Uses pattern matching and heuristics to identify important information.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .models import ExtractedMemory, MemoryType

# Patterns for extracting different types of information
EXTRACTION_PATTERNS: dict[str, dict] = {
    # Decisions and choices made
    "decision": {
        "patterns": [
            r"(?:we |i )?(?:decided|chose|went with|selected|picked)\s+(?:to\s+)?(.+?)(?:\.|$)",
            r"(?:the decision is|decision:)\s*(.+?)(?:\.|$)",
            r"(?:final choice|chosen approach):\s*(.+?)(?:\.|$)",
        ],
        "type": MemoryType.EPISODIC,
        "importance": 7,
        "confidence": 0.8,
    },
    # Facts and definitions
    "fact": {
        "patterns": [
            r"(?:this |the )?(\w+(?:\s+\w+)?)\s+(?:is|are)\s+(.+?)(?:\.|$)",
            r"(\w+(?:\s+\w+)?)\s+(?:uses|has|contains|requires)\s+(.+?)(?:\.|$)",
        ],
        "type": MemoryType.SEMANTIC,
        "importance": 5,
        "confidence": 0.5,  # Lower confidence, needs validation
    },
    # Important notes and reminders
    "note": {
        "patterns": [
            r"(?:note:|important:|remember:|key point:)\s*(.+?)(?:\.|$)",
            r"(?:don't forget|keep in mind|be aware)(?:\s+that)?\s*(.+?)(?:\.|$)",
        ],
        "type": MemoryType.SEMANTIC,
        "importance": 7,
        "confidence": 0.9,
    },
    # Patterns and conventions
    "pattern": {
        "patterns": [
            r"(?:pattern|convention|standard|approach)(?:\s+is)?:\s*(.+?)(?:\.|$)",
            r"(?:we use|we follow|the convention is)\s+(.+?)(?:\.|$)",
            r"(?:best practice|recommended):\s*(.+?)(?:\.|$)",
        ],
        "type": MemoryType.PROCEDURAL,
        "importance": 6,
        "confidence": 0.8,
    },
    # Solutions to problems
    "solution": {
        "patterns": [
            r"(?:fixed by|solved by|solution:|fix:)\s*(.+?)(?:\.|$)",
            r"(?:the fix is|to fix this|to solve this)\s*(.+?)(?:\.|$)",
            r"(?:resolved by|workaround:)\s*(.+?)(?:\.|$)",
        ],
        "type": MemoryType.PROCEDURAL,
        "importance": 8,
        "confidence": 0.85,
    },
    # Configuration and setup
    "config": {
        "patterns": [
            r"(?:configure|set|use)\s+(.+?)\s+(?:to|as|for)\s+(.+?)(?:\.|$)",
            r"(?:setting|config|configuration):\s*(.+?)(?:\.|$)",
        ],
        "type": MemoryType.PROCEDURAL,
        "importance": 6,
        "confidence": 0.7,
    },
    # Error patterns
    "error": {
        "patterns": [
            r"(?:error|issue|problem|bug):\s*(.+?)(?:\.|$)",
            r"(?:fails when|breaks if|doesn't work)\s+(.+?)(?:\.|$)",
        ],
        "type": MemoryType.EPISODIC,
        "importance": 7,
        "confidence": 0.75,
    },
}

# Minimum content length for extraction
MIN_CONTENT_LENGTH = 20

# Maximum content length for a single memory
MAX_CONTENT_LENGTH = 500


@dataclass
class ExtractionResult:
    """Result of memory extraction from a response."""

    extracted: list[ExtractedMemory] = field(default_factory=list)
    total_found: int = 0
    filtered_count: int = 0


class MemoryExtractor:
    """Extracts memories from LLM responses using pattern matching."""

    def __init__(
        self,
        min_confidence: float = 0.6,
        min_content_length: int = MIN_CONTENT_LENGTH,
        max_content_length: int = MAX_CONTENT_LENGTH,
        deduplicate: bool = True,
    ):
        """Initialize extractor with configuration.

        Args:
            min_confidence: Minimum confidence threshold (0-1).
            min_content_length: Minimum content length to extract.
            max_content_length: Maximum content length per memory.
            deduplicate: Whether to remove near-duplicate extractions.
        """
        self.min_confidence = min_confidence
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length
        self.deduplicate_enabled = deduplicate

        # Compile all patterns
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for category, config in EXTRACTION_PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE) for p in config["patterns"]
            ]

    def extract(
        self,
        response: str,
        context: str = "",
        task: str = "",
    ) -> ExtractionResult:
        """Extract potential memories from an LLM response.

        Args:
            response: The LLM response text.
            context: Additional context about the conversation.
            task: The original task/prompt.

        Returns:
            ExtractionResult with extracted memories.
        """
        result = ExtractionResult()
        candidates: list[ExtractedMemory] = []

        for category, patterns in self._compiled_patterns.items():
            config = EXTRACTION_PATTERNS[category]

            for pattern in patterns:
                for match in pattern.finditer(response):
                    # Get the captured content
                    groups = match.groups()
                    if len(groups) == 1:
                        content = groups[0]
                    elif len(groups) == 2:
                        # For patterns with two groups (e.g., "X is Y")
                        content = f"{groups[0]}: {groups[1]}"
                    else:
                        continue

                    content = self._clean_content(content)

                    if not self._is_valid_content(content):
                        continue

                    # Create extracted memory
                    memory = ExtractedMemory(
                        content=content,
                        memory_type=config["type"],
                        confidence=config["confidence"],
                        suggested_importance=config["importance"],
                        suggested_key=self._generate_key(content, category),
                        suggested_tags=[category],
                        source_context=self._get_surrounding_context(response, match),
                    )

                    candidates.append(memory)

        result.total_found = len(candidates)

        # Filter by confidence
        candidates = [m for m in candidates if m.confidence >= self.min_confidence]

        # Deduplicate
        if self.deduplicate_enabled:
            candidates = self._deduplicate(candidates)

        result.extracted = candidates
        result.filtered_count = result.total_found - len(candidates)

        return result

    def _clean_content(self, content: str) -> str:
        """Clean extracted content."""
        # Remove extra whitespace
        content = " ".join(content.split())
        # Remove leading/trailing punctuation
        content = content.strip(".,;:!?-")
        # Truncate if too long
        if len(content) > self.max_content_length:
            content = content[: self.max_content_length].rsplit(" ", 1)[0] + "..."
        return content

    def _is_valid_content(self, content: str) -> bool:
        """Check if content is valid for extraction."""
        if len(content) < self.min_content_length:
            return False

        # Skip if mostly code
        if content.count("(") > 3 or content.count("{") > 3:
            return False

        # Skip if mostly numbers
        if sum(c.isdigit() for c in content) > len(content) * 0.5:
            return False

        return True

    def _generate_key(self, content: str, category: str) -> str:
        """Generate a unique key for the memory."""
        # Create hash from content
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]

        # Extract first few words for readability
        words = content.split()[:3]
        prefix = "-".join(w.lower() for w in words if w.isalnum())[:20]

        return f"auto:{category}:{prefix}:{content_hash}"

    def _get_surrounding_context(
        self,
        text: str,
        match: re.Match,
        context_chars: int = 100,
    ) -> str:
        """Get text surrounding the match for context."""
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)

        context = text[start:end]
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    def _deduplicate(self, memories: list[ExtractedMemory]) -> list[ExtractedMemory]:
        """Remove near-duplicate memories."""
        if not memories:
            return memories

        unique: list[ExtractedMemory] = []
        seen_hashes: set[str] = set()

        for memory in memories:
            # Create normalized hash for comparison
            normalized = memory.content.lower()
            normalized = re.sub(r"\s+", " ", normalized)
            content_hash = hashlib.md5(normalized.encode()).hexdigest()

            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique.append(memory)

        return unique

    def score_importance(
        self,
        content: str,
        context: str = "",
        task: str = "",
    ) -> int:
        """Score the importance of extracted content.

        Args:
            content: The extracted content.
            context: Conversation context.
            task: Original task.

        Returns:
            Importance score from 1-10.
        """
        score = 5  # Base score

        content_lower = content.lower()

        # Boost for action-oriented content
        if any(word in content_lower for word in ["must", "should", "always", "never"]):
            score += 1

        # Boost for specific patterns
        if any(word in content_lower for word in ["error", "fix", "solution", "bug"]):
            score += 2

        # Boost if content relates to task
        if task:
            task_words = set(task.lower().split())
            content_words = set(content_lower.split())
            overlap = len(task_words & content_words)
            if overlap >= 2:
                score += 1

        # Penalize very short content
        if len(content) < 50:
            score -= 1

        return max(1, min(10, score))


def extract_from_response(
    response: str,
    min_confidence: float = 0.6,
    context: str = "",
    task: str = "",
) -> list[ExtractedMemory]:
    """Convenience function to extract memories from a response.

    Args:
        response: The LLM response text.
        min_confidence: Minimum confidence threshold.
        context: Additional context.
        task: Original task.

    Returns:
        List of extracted memories.
    """
    extractor = MemoryExtractor(min_confidence=min_confidence)
    result = extractor.extract(response, context=context, task=task)
    return result.extracted
