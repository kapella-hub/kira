"""Deep Reasoning Engine - Multi-phase thinking with self-critique and refinement."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, AsyncIterator, Callable

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import (
    Analysis,
    Approach,
    Complexity,
    Critique,
    ExecutionPlan,
    ExecutionStep,
    Exploration,
    RefinedPlan,
    TaskUnderstanding,
    ThinkingPhase,
    ThinkingResult,
    Verification,
)

if TYPE_CHECKING:
    from ..core.client import KiraClient
    from ..memory.store import MemoryStore


# Phase-specific model recommendations
# Simpler phases use faster models, critical phases use best models
PHASE_MODELS = {
    ThinkingPhase.UNDERSTAND: "fast",    # Quick comprehension
    ThinkingPhase.EXPLORE: "smart",      # Needs creativity
    ThinkingPhase.ANALYZE: "smart",      # Balanced analysis
    ThinkingPhase.PLAN: "smart",         # Structured planning
    ThinkingPhase.CRITIQUE: "best",      # Critical evaluation needs depth
    ThinkingPhase.REFINE: "best",        # Final refinement needs quality
    ThinkingPhase.VERIFY: "smart",       # Systematic check
}

# Confidence threshold for loop-back
CONFIDENCE_LOOP_BACK_THRESHOLD = 0.5  # If critique < 50%, re-explore

# Maximum loop-back iterations to prevent infinite loops
MAX_LOOP_BACKS = 2


class DeepReasoning:
    """Multi-phase reasoning engine.

    Implements a comprehensive thinking process:
    1. UNDERSTAND - Deep understanding of the task
    2. EXPLORE - Brainstorm multiple approaches
    3. ANALYZE - Evaluate and choose best approach
    4. PLAN - Create detailed execution plan
    5. CRITIQUE - Self-critique the plan
    6. REFINE - Improve based on critique
    7. VERIFY - Validate plan against requirements (new)

    Features:
    - Adaptive phases: Skips exploration/critique for trivial tasks
    - Confidence loop-back: Re-explores if critique finds low confidence
    - Phase-specific models: Uses appropriate models per phase
    - Memory-informed: Pulls relevant past reasoning from memory
    - Streaming output: Shows each phase as it completes
    """

    def __init__(
        self,
        kiro_client: "KiraClient",
        console: Console | None = None,
        verbose: bool = True,
        memory_store: "MemoryStore | None" = None,
        use_phase_models: bool = True,
    ):
        self.client = kiro_client
        self.console = console or Console()
        self.verbose = verbose
        self.memory = memory_store
        self.use_phase_models = use_phase_models
        self._original_model = kiro_client.model

    def _set_phase_model(self, phase: ThinkingPhase) -> None:
        """Set the model appropriate for this phase."""
        if not self.use_phase_models:
            return

        model_tier = PHASE_MODELS.get(phase, "smart")
        # Map tier to actual model name
        model_map = {
            "fast": "claude-3-haiku",
            "smart": "claude-sonnet-4",
            "best": "claude-opus-4",
        }
        self.client.model = model_map.get(model_tier, self._original_model)

    def _restore_model(self) -> None:
        """Restore the original model setting."""
        self.client.model = self._original_model

    def _get_memory_context(self, task: str) -> str:
        """Pull relevant past reasoning from memory."""
        if not self.memory:
            return ""

        try:
            # Search for similar past tasks
            memories = self.memory.search(task, tags=["reasoning", "plan"], limit=3)
            if not memories:
                return ""

            context_parts = ["## Past Reasoning (similar tasks)\n"]
            for mem in memories:
                context_parts.append(f"- {mem.key}: {mem.content[:200]}...")

            return "\n".join(context_parts)
        except Exception:
            return ""

    def _detect_trivial_task(self, task: str) -> bool:
        """Detect if a task is trivial (should skip exploration/critique).

        Only returns True for VERY simple tasks like:
        - Single-line fixes
        - Simple questions
        - Typo corrections
        - Adding a single log statement
        """
        task_lower = task.lower()

        # Trivial indicators (must match multiple)
        trivial_patterns = [
            r"\b(typo|spelling|rename)\b",
            r"\b(add|remove)\s+(a\s+)?(log|print|console)\b",
            r"\b(what|where|how)\s+(is|are|does)\b",  # Simple questions
            r"^(fix|change|update)\s+\w+\s+to\s+\w+$",  # Simple substitutions
        ]

        # Complex indicators (any match = not trivial)
        complex_patterns = [
            r"\b(implement|design|architect|build|create|develop)\b",
            r"\b(refactor|optimize|improve|enhance)\b",
            r"\b(api|database|auth|security)\b",
            r"\b(multiple|several|many|all)\b",
            r"\b(system|service|module|component)\b",
        ]

        # Check for complexity first
        for pattern in complex_patterns:
            if re.search(pattern, task_lower):
                return False

        # Count trivial indicators
        trivial_count = sum(1 for p in trivial_patterns if re.search(p, task_lower))

        # Must have at least 1 trivial indicator AND short task
        return trivial_count >= 1 and len(task.split()) < 15

    async def think(
        self,
        task: str,
        context: str = "",
        on_phase_complete: Callable[[ThinkingPhase, str], None] | None = None,
        force_full: bool = False,  # Force all phases even for simple tasks
    ) -> ThinkingResult:
        """Run the complete thinking process.

        Args:
            task: The task to think about
            context: Additional context (e.g., memory, codebase info)
            on_phase_complete: Callback when each phase completes
            force_full: If True, runs all phases regardless of complexity

        Returns:
            Complete ThinkingResult with all phases
        """
        start_time = time.time()
        result = ThinkingResult(task=task)

        # Enhance context with memory-informed reasoning
        memory_context = self._get_memory_context(task)
        if memory_context:
            context = f"{context}\n\n{memory_context}" if context else memory_context

        # Detect if task is trivial (very simple)
        is_trivial = not force_full and self._detect_trivial_task(task)
        if is_trivial:
            result.was_simplified = True
            if self.verbose:
                self.console.print(
                    "[dim]Task detected as trivial - using simplified reasoning[/dim]"
                )

        try:
            # Phase 1: Understand (always runs)
            self._set_phase_model(ThinkingPhase.UNDERSTAND)
            if self.verbose:
                self.console.print("\n[bold cyan]Phase 1: Understanding the task...[/bold cyan]")
            result.understanding = await self._phase_understand(task, context)
            result.phases_completed.append(ThinkingPhase.UNDERSTAND)
            if on_phase_complete:
                on_phase_complete(ThinkingPhase.UNDERSTAND, result.understanding.raw_output)
            if self.verbose:
                self._display_understanding(result.understanding)

            if is_trivial:
                # Simplified path: UNDERSTAND → PLAN only
                self._set_phase_model(ThinkingPhase.PLAN)
                if self.verbose:
                    self.console.print("\n[bold cyan]Phase 2: Creating execution plan...[/bold cyan]")

                # Create a simple analysis for the plan phase
                simple_analysis = Analysis(
                    chosen_approach="Direct implementation",
                    detailed_reasoning="Task is straightforward - proceeding with direct implementation.",
                    raw_output="",
                )
                result.initial_plan = await self._phase_plan(
                    task, result.understanding, simple_analysis, context
                )
                result.phases_completed.append(ThinkingPhase.PLAN)
                if on_phase_complete:
                    on_phase_complete(ThinkingPhase.PLAN, result.initial_plan.raw_output)
                if self.verbose:
                    self._display_plan(result.initial_plan)

                # Set refined plan to initial plan for trivial tasks
                result.refined_plan = RefinedPlan(
                    original_plan=result.initial_plan,
                    final_steps=result.initial_plan.steps,
                    final_summary=result.initial_plan.summary,
                    confidence_score=0.9,
                    raw_output="",
                )

            else:
                # Full reasoning path with potential loop-back
                await self._run_full_reasoning(task, context, result, on_phase_complete)

            result.total_thinking_time = time.time() - start_time
            return result

        finally:
            self._restore_model()

    async def _run_full_reasoning(
        self,
        task: str,
        context: str,
        result: ThinkingResult,
        on_phase_complete: Callable[[ThinkingPhase, str], None] | None,
    ) -> None:
        """Run full reasoning with potential loop-back on low confidence."""
        loop_back_count = 0

        while True:
            # Phase 2: Explore
            self._set_phase_model(ThinkingPhase.EXPLORE)
            if self.verbose:
                phase_num = 2 + (loop_back_count * 4)  # Adjust numbering on loop-back
                self.console.print(f"\n[bold cyan]Phase {phase_num}: Exploring approaches...[/bold cyan]")
            result.exploration = await self._phase_explore(task, result.understanding, context)
            if ThinkingPhase.EXPLORE not in result.phases_completed:
                result.phases_completed.append(ThinkingPhase.EXPLORE)
            if on_phase_complete:
                on_phase_complete(ThinkingPhase.EXPLORE, result.exploration.raw_output)
            if self.verbose:
                self._display_exploration(result.exploration)

            # Phase 3: Analyze
            self._set_phase_model(ThinkingPhase.ANALYZE)
            if self.verbose:
                phase_num = 3 + (loop_back_count * 4)
                self.console.print(f"\n[bold cyan]Phase {phase_num}: Analyzing approaches...[/bold cyan]")
            result.analysis = await self._phase_analyze(
                task, result.understanding, result.exploration, context
            )
            if ThinkingPhase.ANALYZE not in result.phases_completed:
                result.phases_completed.append(ThinkingPhase.ANALYZE)
            if on_phase_complete:
                on_phase_complete(ThinkingPhase.ANALYZE, result.analysis.raw_output)
            if self.verbose:
                self._display_analysis(result.analysis)

            # Phase 4: Plan
            self._set_phase_model(ThinkingPhase.PLAN)
            if self.verbose:
                phase_num = 4 + (loop_back_count * 4)
                self.console.print(f"\n[bold cyan]Phase {phase_num}: Creating execution plan...[/bold cyan]")
            result.initial_plan = await self._phase_plan(
                task, result.understanding, result.analysis, context
            )
            if ThinkingPhase.PLAN not in result.phases_completed:
                result.phases_completed.append(ThinkingPhase.PLAN)
            if on_phase_complete:
                on_phase_complete(ThinkingPhase.PLAN, result.initial_plan.raw_output)
            if self.verbose:
                self._display_plan(result.initial_plan)

            # Phase 5: Critique
            self._set_phase_model(ThinkingPhase.CRITIQUE)
            if self.verbose:
                phase_num = 5 + (loop_back_count * 4)
                self.console.print(f"\n[bold cyan]Phase {phase_num}: Self-critique...[/bold cyan]")
            result.critique = await self._phase_critique(
                task, result.initial_plan, result.understanding, context
            )
            if ThinkingPhase.CRITIQUE not in result.phases_completed:
                result.phases_completed.append(ThinkingPhase.CRITIQUE)
            if on_phase_complete:
                on_phase_complete(ThinkingPhase.CRITIQUE, result.critique.raw_output)
            if self.verbose:
                self._display_critique(result.critique)

            # Check if we need to loop back due to low confidence
            if (
                result.critique.confidence_score < CONFIDENCE_LOOP_BACK_THRESHOLD
                and loop_back_count < MAX_LOOP_BACKS
            ):
                loop_back_count += 1
                result.loop_back_count = loop_back_count
                if self.verbose:
                    self.console.print(
                        f"\n[bold yellow]⚠ Low confidence ({result.critique.confidence_score:.0%}) - "
                        f"looping back to explore alternatives (attempt {loop_back_count}/{MAX_LOOP_BACKS})[/bold yellow]"
                    )
                # Add critique feedback to context for next iteration
                context = f"{context}\n\n## Previous Critique (improve on this)\n"
                context += f"Weaknesses: {', '.join(result.critique.weaknesses)}\n"
                context += f"Blind spots: {', '.join(result.critique.blind_spots)}\n"
                continue  # Loop back to EXPLORE

            # Confidence is acceptable or max loop-backs reached
            break

        # Phase 6: Refine
        self._set_phase_model(ThinkingPhase.REFINE)
        if self.verbose:
            self.console.print("\n[bold cyan]Phase 6: Refining plan...[/bold cyan]")
        result.refined_plan = await self._phase_refine(
            task, result.initial_plan, result.critique, context
        )
        result.phases_completed.append(ThinkingPhase.REFINE)
        if on_phase_complete:
            on_phase_complete(ThinkingPhase.REFINE, result.refined_plan.raw_output)
        if self.verbose:
            self._display_refined_plan(result.refined_plan)

        # Phase 7: Verify (new)
        self._set_phase_model(ThinkingPhase.VERIFY)
        if self.verbose:
            self.console.print("\n[bold cyan]Phase 7: Verifying against requirements...[/bold cyan]")
        result.verification = await self._phase_verify(
            task, result.understanding, result.refined_plan, context
        )
        result.phases_completed.append(ThinkingPhase.VERIFY)
        if on_phase_complete:
            on_phase_complete(ThinkingPhase.VERIFY, result.verification.raw_output)
        if self.verbose:
            self._display_verification(result.verification)

    # =========================================================================
    # Phase 1: Understand
    # =========================================================================

    async def _phase_understand(
        self, task: str, context: str
    ) -> TaskUnderstanding:
        """Phase 1: Deeply understand the task."""
        prompt = f"""You are a senior engineer analyzing a task before implementation.

Your goal is to deeply understand what is being asked, including implicit requirements.

## Context
{context if context else "No additional context provided."}

## Task
{task}

## Instructions
Think deeply about this task. Consider:
- What is the core goal?
- What are the implicit requirements not explicitly stated?
- What constraints exist?
- What assumptions are we making?
- What unknowns or ambiguities exist?
- How will we know if we succeeded?

Output your analysis in this EXACT format:

[UNDERSTAND:core_goal]
<One clear sentence describing the fundamental goal>

[UNDERSTAND:implicit_requirements]
- <Requirement 1>
- <Requirement 2>
- <Add more as needed>

[UNDERSTAND:constraints]
- <Constraint 1>
- <Constraint 2>
- <Add more as needed>

[UNDERSTAND:assumptions]
- <Assumption 1>
- <Assumption 2>
- <Add more as needed>

[UNDERSTAND:unknowns]
- <Unknown/ambiguity 1>
- <Unknown/ambiguity 2>
- <Add more as needed>

[UNDERSTAND:success_criteria]
- <How to verify success 1>
- <How to verify success 2>
- <Add more as needed>

[UNDERSTAND:end]

Now analyze the task:"""

        result = await self.client.run_batch(prompt)
        return self._parse_understanding(result.output)

    def _parse_understanding(self, output: str) -> TaskUnderstanding:
        """Parse understanding from LLM output."""
        # Extract core goal
        goal_match = re.search(
            r"\[UNDERSTAND:core_goal\]\s*(.+?)(?=\[UNDERSTAND:|$)", output, re.DOTALL
        )
        core_goal = goal_match.group(1).strip() if goal_match else "Goal not identified"

        # Helper to extract bullet lists
        def extract_list(marker: str) -> list[str]:
            pattern = rf"\[UNDERSTAND:{marker}\]\s*(.+?)(?=\[UNDERSTAND:|$)"
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                items = re.findall(r"^[-*]\s*(.+)$", match.group(1), re.MULTILINE)
                return [item.strip() for item in items if item.strip()]
            return []

        return TaskUnderstanding(
            core_goal=core_goal,
            implicit_requirements=extract_list("implicit_requirements"),
            constraints=extract_list("constraints"),
            assumptions=extract_list("assumptions"),
            unknowns=extract_list("unknowns"),
            success_criteria=extract_list("success_criteria"),
            raw_output=output,
        )

    # =========================================================================
    # Phase 2: Explore
    # =========================================================================

    async def _phase_explore(
        self, task: str, understanding: TaskUnderstanding, context: str
    ) -> Exploration:
        """Phase 2: Brainstorm multiple approaches."""
        prompt = f"""You are brainstorming approaches to solve a task.

## Task
{task}

## Understanding
Core Goal: {understanding.core_goal}
Constraints: {', '.join(understanding.constraints) if understanding.constraints else 'None identified'}
Success Criteria: {', '.join(understanding.success_criteria) if understanding.success_criteria else 'Task completed correctly'}

## Context
{context if context else "No additional context."}

## Instructions
Brainstorm 3-4 different approaches to solve this task. For each approach, consider:
- Brief description of the approach
- Pros (advantages)
- Cons (disadvantages)
- Risk level (low/medium/high)

Then recommend which approach is best and why.

Output in this EXACT format:

[EXPLORE:approach_1]
Name: <Approach name>
Description: <Brief description>
Pros:
- <Pro 1>
- <Pro 2>
Cons:
- <Con 1>
- <Con 2>
Risk: <low/medium/high>

[EXPLORE:approach_2]
Name: <Approach name>
Description: <Brief description>
Pros:
- <Pro 1>
- <Pro 2>
Cons:
- <Con 1>
- <Con 2>
Risk: <low/medium/high>

[EXPLORE:approach_3]
Name: <Approach name>
Description: <Brief description>
Pros:
- <Pro 1>
- <Pro 2>
Cons:
- <Con 1>
- <Con 2>
Risk: <low/medium/high>

[EXPLORE:recommendation]
Recommended: <Name of recommended approach>
Reasoning: <Why this approach is best>

[EXPLORE:end]

Now brainstorm approaches:"""

        result = await self.client.run_batch(prompt)
        return self._parse_exploration(result.output)

    def _parse_exploration(self, output: str) -> Exploration:
        """Parse exploration from LLM output."""
        approaches = []

        # Find all approach blocks
        approach_pattern = r"\[EXPLORE:approach_\d+\]\s*(.+?)(?=\[EXPLORE:|$)"
        approach_matches = re.findall(approach_pattern, output, re.DOTALL | re.IGNORECASE)

        for match in approach_matches:
            name_match = re.search(r"Name:\s*(.+?)(?=\n|$)", match)
            desc_match = re.search(r"Description:\s*(.+?)(?=Pros:|$)", match, re.DOTALL)
            risk_match = re.search(r"Risk:\s*(\w+)", match, re.IGNORECASE)

            # Extract pros
            pros_section = re.search(r"Pros:\s*(.+?)(?=Cons:|$)", match, re.DOTALL)
            pros = []
            if pros_section:
                pros = re.findall(r"^[-*]\s*(.+)$", pros_section.group(1), re.MULTILINE)
                pros = [p.strip() for p in pros if p.strip()]

            # Extract cons
            cons_section = re.search(r"Cons:\s*(.+?)(?=Risk:|$)", match, re.DOTALL)
            cons = []
            if cons_section:
                cons = re.findall(r"^[-*]\s*(.+)$", cons_section.group(1), re.MULTILINE)
                cons = [c.strip() for c in cons if c.strip()]

            if name_match:
                approaches.append(
                    Approach(
                        name=name_match.group(1).strip(),
                        description=desc_match.group(1).strip() if desc_match else "",
                        pros=pros,
                        cons=cons,
                        risk_level=risk_match.group(1).lower() if risk_match else "medium",
                    )
                )

        # Extract recommendation
        rec_match = re.search(
            r"\[EXPLORE:recommendation\]\s*(.+?)(?=\[EXPLORE:|$)", output, re.DOTALL
        )
        recommended = ""
        reasoning = ""
        if rec_match:
            rec_text = rec_match.group(1)
            name_match = re.search(r"Recommended:\s*(.+?)(?=\n|$)", rec_text)
            reason_match = re.search(r"Reasoning:\s*(.+?)(?=$)", rec_text, re.DOTALL)
            if name_match:
                recommended = name_match.group(1).strip()
            if reason_match:
                reasoning = reason_match.group(1).strip()

        # Mark recommended approach
        for approach in approaches:
            if approach.name.lower() == recommended.lower():
                approach.recommended = True

        return Exploration(
            approaches=approaches,
            recommended_approach=recommended,
            reasoning=reasoning,
            raw_output=output,
        )

    # =========================================================================
    # Phase 3: Analyze
    # =========================================================================

    async def _phase_analyze(
        self,
        task: str,
        understanding: TaskUnderstanding,
        exploration: Exploration,
        context: str,
    ) -> Analysis:
        """Phase 3: Deep analysis of chosen approach."""
        approaches_text = ""
        for i, approach in enumerate(exploration.approaches, 1):
            approaches_text += f"\n{i}. {approach.name}: {approach.description}"
            approaches_text += f"\n   Pros: {', '.join(approach.pros)}"
            approaches_text += f"\n   Cons: {', '.join(approach.cons)}"
            approaches_text += f"\n   Risk: {approach.risk_level}"

        prompt = f"""You are doing deep analysis to validate the chosen approach.

## Task
{task}

## Core Goal
{understanding.core_goal}

## Explored Approaches
{approaches_text}

## Recommended Approach
{exploration.recommended_approach}
Reasoning: {exploration.reasoning}

## Context
{context if context else "No additional context."}

## Instructions
Analyze the recommended approach in depth:
1. Validate it's the right choice
2. Identify potential issues that could arise
3. Plan mitigations for each issue
4. Identify dependencies

Output in this EXACT format:

[ANALYZE:chosen_approach]
<Name of the chosen approach>

[ANALYZE:detailed_reasoning]
<Detailed explanation of why this approach is correct, addressing any concerns>

[ANALYZE:potential_issues]
- <Issue 1 that could arise>
- <Issue 2 that could arise>
- <Add more as needed>

[ANALYZE:mitigations]
- <Mitigation for issue 1>
- <Mitigation for issue 2>
- <Add more as needed>

[ANALYZE:dependencies]
- <Dependency 1>
- <Dependency 2>
- <Add more as needed>

[ANALYZE:end]

Now analyze:"""

        result = await self.client.run_batch(prompt)
        return self._parse_analysis(result.output)

    def _parse_analysis(self, output: str) -> Analysis:
        """Parse analysis from LLM output."""
        # Extract chosen approach
        chosen_match = re.search(
            r"\[ANALYZE:chosen_approach\]\s*(.+?)(?=\[ANALYZE:|$)", output, re.DOTALL
        )
        chosen = chosen_match.group(1).strip() if chosen_match else ""

        # Extract detailed reasoning
        reasoning_match = re.search(
            r"\[ANALYZE:detailed_reasoning\]\s*(.+?)(?=\[ANALYZE:|$)", output, re.DOTALL
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""

        # Helper to extract lists
        def extract_list(marker: str) -> list[str]:
            pattern = rf"\[ANALYZE:{marker}\]\s*(.+?)(?=\[ANALYZE:|$)"
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                items = re.findall(r"^[-*]\s*(.+)$", match.group(1), re.MULTILINE)
                return [item.strip() for item in items if item.strip()]
            return []

        return Analysis(
            chosen_approach=chosen,
            detailed_reasoning=reasoning,
            potential_issues=extract_list("potential_issues"),
            mitigations=extract_list("mitigations"),
            dependencies=extract_list("dependencies"),
            raw_output=output,
        )

    # =========================================================================
    # Phase 4: Plan
    # =========================================================================

    async def _phase_plan(
        self,
        task: str,
        understanding: TaskUnderstanding,
        analysis: Analysis,
        context: str,
    ) -> ExecutionPlan:
        """Phase 4: Create detailed execution plan."""
        prompt = f"""You are creating a detailed execution plan.

## Task
{task}

## Core Goal
{understanding.core_goal}

## Chosen Approach
{analysis.chosen_approach}

## Reasoning
{analysis.detailed_reasoning}

## Known Issues & Mitigations
Issues: {', '.join(analysis.potential_issues) if analysis.potential_issues else 'None identified'}
Mitigations: {', '.join(analysis.mitigations) if analysis.mitigations else 'None needed'}

## Dependencies
{', '.join(analysis.dependencies) if analysis.dependencies else 'None'}

## Context
{context if context else "No additional context."}

## Instructions
Create a detailed, step-by-step execution plan. Each step should be:
- Specific and actionable
- Include expected outcome
- Include how to verify success

Output in this EXACT format:

[PLAN:summary]
<One sentence summary of the plan>

[PLAN:complexity]
<trivial/simple/moderate/complex/very_complex>

[PLAN:effort]
<quick/medium/significant/major>

[PLAN:prerequisites]
- <Prerequisite 1>
- <Prerequisite 2>

[PLAN:steps]
1. <Action to take>
   Details: <Specific details about how to do this>
   Expected: <What should happen when done>
   Verify: <How to verify this step succeeded>

2. <Action to take>
   Details: <Specific details>
   Expected: <Expected outcome>
   Verify: <Verification method>

3. <Continue for all steps needed>

[PLAN:end]

Now create the plan:"""

        result = await self.client.run_batch(prompt)
        return self._parse_plan(result.output)

    def _parse_plan(self, output: str) -> ExecutionPlan:
        """Parse execution plan from LLM output."""
        # Extract summary
        summary_match = re.search(
            r"\[PLAN:summary\]\s*(.+?)(?=\[PLAN:|$)", output, re.DOTALL
        )
        summary = summary_match.group(1).strip() if summary_match else ""

        # Extract complexity
        complexity_match = re.search(r"\[PLAN:complexity\]\s*(\w+)", output, re.IGNORECASE)
        complexity = Complexity.MODERATE
        if complexity_match:
            complexity = Complexity.from_string(complexity_match.group(1))

        # Extract effort
        effort_match = re.search(r"\[PLAN:effort\]\s*(\w+)", output, re.IGNORECASE)
        effort = effort_match.group(1).strip() if effort_match else "medium"

        # Extract prerequisites
        prereq_match = re.search(
            r"\[PLAN:prerequisites\]\s*(.+?)(?=\[PLAN:|$)", output, re.DOTALL
        )
        prerequisites = []
        if prereq_match:
            prerequisites = re.findall(r"^[-*]\s*(.+)$", prereq_match.group(1), re.MULTILINE)
            prerequisites = [p.strip() for p in prerequisites if p.strip()]

        # Extract steps
        steps_match = re.search(
            r"\[PLAN:steps\]\s*(.+?)(?=\[PLAN:end|$)", output, re.DOTALL | re.IGNORECASE
        )
        steps = []
        if steps_match:
            steps_text = steps_match.group(1)
            # Match step blocks
            step_pattern = r"(\d+)\.\s*(.+?)(?=\n\d+\.|$)"
            step_matches = re.findall(step_pattern, steps_text, re.DOTALL)

            for num, content in step_matches:
                # Parse step content
                lines = content.strip().split("\n")
                action = lines[0].strip() if lines else ""

                details = ""
                expected = ""
                verify = ""

                for line in lines[1:]:
                    line = line.strip()
                    if line.lower().startswith("details:"):
                        details = line[8:].strip()
                    elif line.lower().startswith("expected:"):
                        expected = line[9:].strip()
                    elif line.lower().startswith("verify:"):
                        verify = line[7:].strip()

                if action:
                    steps.append(
                        ExecutionStep(
                            number=int(num),
                            action=action,
                            details=details,
                            expected_outcome=expected,
                            verification=verify,
                        )
                    )

        return ExecutionPlan(
            summary=summary,
            complexity=complexity,
            steps=steps,
            prerequisites=prerequisites,
            estimated_effort=effort,
            raw_output=output,
        )

    # =========================================================================
    # Phase 5: Critique
    # =========================================================================

    async def _phase_critique(
        self,
        task: str,
        plan: ExecutionPlan,
        understanding: TaskUnderstanding,
        context: str,
    ) -> Critique:
        """Phase 5: Self-critique the plan."""
        steps_text = ""
        for step in plan.steps:
            steps_text += f"\n{step.number}. {step.action}"
            if step.details:
                steps_text += f"\n   Details: {step.details}"

        prompt = f"""You are a critical reviewer examining an execution plan.

Your job is to find weaknesses, blind spots, and potential improvements.
Be thorough and critical - it's better to find issues now than during execution.

## Original Task
{task}

## Core Goal
{understanding.core_goal}

## Success Criteria
{chr(10).join('- ' + c for c in understanding.success_criteria) if understanding.success_criteria else 'Not specified'}

## The Plan
Summary: {plan.summary}
Complexity: {plan.complexity.value}
Effort: {plan.estimated_effort}

Steps:
{steps_text}

## Context
{context if context else "No additional context."}

## Instructions
Critically evaluate this plan:
1. What are its strengths?
2. What are its weaknesses?
3. What blind spots might we have?
4. What specific improvements would make it better?
5. How confident are you in this plan (0-100%)?

Be specific and actionable in your critique.

Output in this EXACT format:

[CRITIQUE:strengths]
- <Strength 1>
- <Strength 2>
- <Add more as needed>

[CRITIQUE:weaknesses]
- <Weakness 1>
- <Weakness 2>
- <Add more as needed>

[CRITIQUE:blind_spots]
- <Blind spot 1>
- <Blind spot 2>
- <Add more as needed>

[CRITIQUE:improvements]
- <Specific improvement 1>
- <Specific improvement 2>
- <Add more as needed>

[CRITIQUE:confidence]
<Number from 0-100>

[CRITIQUE:end]

Now critique the plan:"""

        result = await self.client.run_batch(prompt)
        return self._parse_critique(result.output)

    def _parse_critique(self, output: str) -> Critique:
        """Parse critique from LLM output."""

        def extract_list(marker: str) -> list[str]:
            pattern = rf"\[CRITIQUE:{marker}\]\s*(.+?)(?=\[CRITIQUE:|$)"
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                items = re.findall(r"^[-*]\s*(.+)$", match.group(1), re.MULTILINE)
                return [item.strip() for item in items if item.strip()]
            return []

        # Extract confidence
        confidence_match = re.search(r"\[CRITIQUE:confidence\]\s*(\d+)", output)
        confidence = 70  # Default
        if confidence_match:
            confidence = min(100, max(0, int(confidence_match.group(1))))

        return Critique(
            strengths=extract_list("strengths"),
            weaknesses=extract_list("weaknesses"),
            blind_spots=extract_list("blind_spots"),
            improvements=extract_list("improvements"),
            confidence_score=confidence / 100.0,
            raw_output=output,
        )

    # =========================================================================
    # Phase 6: Refine
    # =========================================================================

    async def _phase_refine(
        self,
        task: str,
        plan: ExecutionPlan,
        critique: Critique,
        context: str,
    ) -> RefinedPlan:
        """Phase 6: Refine plan based on critique."""
        steps_text = ""
        for step in plan.steps:
            steps_text += f"\n{step.number}. {step.action}"
            if step.details:
                steps_text += f"\n   Details: {step.details}"

        prompt = f"""You are refining an execution plan based on critical feedback.

## Original Task
{task}

## Original Plan
Summary: {plan.summary}
Steps:
{steps_text}

## Critique Results
Strengths:
{chr(10).join('- ' + s for s in critique.strengths) if critique.strengths else '- None identified'}

Weaknesses:
{chr(10).join('- ' + w for w in critique.weaknesses) if critique.weaknesses else '- None identified'}

Blind Spots:
{chr(10).join('- ' + b for b in critique.blind_spots) if critique.blind_spots else '- None identified'}

Suggested Improvements:
{chr(10).join('- ' + i for i in critique.improvements) if critique.improvements else '- None suggested'}

Initial Confidence: {critique.confidence_score:.0%}

## Context
{context if context else "No additional context."}

## Instructions
Create an improved plan that addresses the weaknesses and blind spots.
Keep what works, fix what doesn't, and add what's missing.

Output in this EXACT format:

[REFINE:summary]
<Updated summary reflecting improvements>

[REFINE:refinements_made]
- <What was changed/improved 1>
- <What was changed/improved 2>
- <Add more as needed>

[REFINE:final_steps]
1. <Refined action>
   Details: <Updated details>
   Verify: <How to verify>

2. <Refined action>
   Details: <Updated details>
   Verify: <How to verify>

<Continue for all steps>

[REFINE:confidence]
<Updated confidence 0-100>

[REFINE:end]

Now refine the plan:"""

        result = await self.client.run_batch(prompt)
        return self._parse_refined_plan(result.output, plan)

    def _parse_refined_plan(self, output: str, original_plan: ExecutionPlan) -> RefinedPlan:
        """Parse refined plan from LLM output."""
        # Extract summary
        summary_match = re.search(
            r"\[REFINE:summary\]\s*(.+?)(?=\[REFINE:|$)", output, re.DOTALL
        )
        summary = summary_match.group(1).strip() if summary_match else original_plan.summary

        # Extract refinements
        refinements_match = re.search(
            r"\[REFINE:refinements_made\]\s*(.+?)(?=\[REFINE:|$)", output, re.DOTALL
        )
        refinements = []
        if refinements_match:
            refinements = re.findall(r"^[-*]\s*(.+)$", refinements_match.group(1), re.MULTILINE)
            refinements = [r.strip() for r in refinements if r.strip()]

        # Extract steps
        steps_match = re.search(
            r"\[REFINE:final_steps\]\s*(.+?)(?=\[REFINE:confidence|$)", output, re.DOTALL
        )
        steps = []
        if steps_match:
            steps_text = steps_match.group(1)
            step_pattern = r"(\d+)\.\s*(.+?)(?=\n\d+\.|$)"
            step_matches = re.findall(step_pattern, steps_text, re.DOTALL)

            for num, content in step_matches:
                lines = content.strip().split("\n")
                action = lines[0].strip() if lines else ""

                details = ""
                verify = ""

                for line in lines[1:]:
                    line = line.strip()
                    if line.lower().startswith("details:"):
                        details = line[8:].strip()
                    elif line.lower().startswith("verify:"):
                        verify = line[7:].strip()

                if action:
                    steps.append(
                        ExecutionStep(
                            number=int(num),
                            action=action,
                            details=details,
                            verification=verify,
                        )
                    )

        # Extract confidence
        confidence_match = re.search(r"\[REFINE:confidence\]\s*(\d+)", output)
        confidence = 80  # Default
        if confidence_match:
            confidence = min(100, max(0, int(confidence_match.group(1))))

        return RefinedPlan(
            original_plan=original_plan,
            refinements_made=refinements,
            final_steps=steps if steps else original_plan.steps,
            final_summary=summary,
            confidence_score=confidence / 100.0,
            raw_output=output,
        )

    # =========================================================================
    # Phase 7: Verify
    # =========================================================================

    async def _phase_verify(
        self,
        task: str,
        understanding: TaskUnderstanding,
        refined_plan: RefinedPlan,
        context: str,
    ) -> Verification:
        """Phase 7: Verify plan against original requirements."""
        steps_text = ""
        for step in refined_plan.final_steps:
            steps_text += f"\n{step.number}. {step.action}"
            if step.details:
                steps_text += f"\n   Details: {step.details}"

        prompt = f"""You are doing a final verification check before execution.

## Original Task
{task}

## Core Goal
{understanding.core_goal}

## Success Criteria
{chr(10).join('- ' + c for c in understanding.success_criteria) if understanding.success_criteria else 'Not specified'}

## Implicit Requirements
{chr(10).join('- ' + r for r in understanding.implicit_requirements) if understanding.implicit_requirements else 'None identified'}

## The Final Plan
Summary: {refined_plan.final_summary}
Steps:
{steps_text}

## Context
{context if context else "No additional context."}

## Instructions
Verify this plan against the original requirements:
1. Which requirements does the plan address?
2. Which requirements might be missing or incomplete?
3. What edge cases does the plan cover?
4. What edge cases might be missing?
5. Are there any blocking issues that would prevent execution?
6. Final confidence: Is this plan ready to execute?

Be thorough - this is the last check before execution.

Output in this EXACT format:

[VERIFY:requirements_met]
- <Requirement that IS addressed by the plan>
- <Add more as needed>

[VERIFY:requirements_missing]
- <Requirement that is NOT addressed or incomplete>
- <Add more as needed, or "None" if all covered>

[VERIFY:edge_cases_covered]
- <Edge case the plan handles>
- <Add more as needed>

[VERIFY:edge_cases_missing]
- <Edge case NOT covered>
- <Add more as needed, or "None" if all covered>

[VERIFY:blocking_issues]
- <Issue that would block execution>
- <Add more as needed, or "None" if ready>

[VERIFY:ready]
<yes/no>

[VERIFY:confidence]
<Number from 0-100>

[VERIFY:end]

Now verify the plan:"""

        result = await self.client.run_batch(prompt)
        return self._parse_verification(result.output)

    def _parse_verification(self, output: str) -> Verification:
        """Parse verification from LLM output."""

        def extract_list(marker: str) -> list[str]:
            pattern = rf"\[VERIFY:{marker}\]\s*(.+?)(?=\[VERIFY:|$)"
            match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if match:
                items = re.findall(r"^[-*]\s*(.+)$", match.group(1), re.MULTILINE)
                items = [item.strip() for item in items if item.strip()]
                # Filter out "None" entries
                return [i for i in items if i.lower() != "none"]
            return []

        # Extract ready status
        ready_match = re.search(r"\[VERIFY:ready\]\s*(\w+)", output, re.IGNORECASE)
        ready = True
        if ready_match:
            ready = ready_match.group(1).lower() in ("yes", "true", "ready")

        # Extract confidence
        confidence_match = re.search(r"\[VERIFY:confidence\]\s*(\d+)", output)
        confidence = 80
        if confidence_match:
            confidence = min(100, max(0, int(confidence_match.group(1))))

        blocking = extract_list("blocking_issues")

        return Verification(
            requirements_met=extract_list("requirements_met"),
            requirements_missing=extract_list("requirements_missing"),
            edge_cases_covered=extract_list("edge_cases_covered"),
            edge_cases_missing=extract_list("edge_cases_missing"),
            ready_to_execute=ready and len(blocking) == 0,
            blocking_issues=blocking,
            final_confidence=confidence / 100.0,
            raw_output=output,
        )

    # =========================================================================
    # Display helpers
    # =========================================================================

    def _display_understanding(self, understanding: TaskUnderstanding) -> None:
        """Display understanding results."""
        content = f"**Core Goal**: {understanding.core_goal}\n"

        if understanding.implicit_requirements:
            content += "\n**Implicit Requirements**:\n"
            for req in understanding.implicit_requirements:
                content += f"  - {req}\n"

        if understanding.constraints:
            content += "\n**Constraints**:\n"
            for con in understanding.constraints:
                content += f"  - {con}\n"

        if understanding.unknowns:
            content += "\n**Unknowns/Ambiguities**:\n"
            for unk in understanding.unknowns:
                content += f"  - {unk}\n"

        self.console.print(Panel(content.strip(), title="Understanding", border_style="green"))

    def _display_exploration(self, exploration: Exploration) -> None:
        """Display exploration results."""
        content = ""
        for approach in exploration.approaches:
            marker = "→ " if approach.recommended else "  "
            content += f"{marker}**{approach.name}** (Risk: {approach.risk_level})\n"
            content += f"  {approach.description}\n"

        content += f"\n**Recommended**: {exploration.recommended_approach}"

        self.console.print(Panel(content.strip(), title="Approaches", border_style="blue"))

    def _display_analysis(self, analysis: Analysis) -> None:
        """Display analysis results."""
        content = f"**Chosen**: {analysis.chosen_approach}\n\n"
        content += f"**Reasoning**: {analysis.detailed_reasoning[:200]}...\n"

        if analysis.potential_issues:
            content += "\n**Potential Issues**:\n"
            for issue in analysis.potential_issues[:3]:
                content += f"  - {issue}\n"

        self.console.print(Panel(content.strip(), title="Analysis", border_style="yellow"))

    def _display_plan(self, plan: ExecutionPlan) -> None:
        """Display execution plan."""
        content = f"**Summary**: {plan.summary}\n"
        content += f"**Complexity**: {plan.complexity.value}\n"
        content += f"**Effort**: {plan.estimated_effort}\n"

        if plan.steps:
            content += "\n**Steps**:\n"
            for step in plan.steps[:5]:  # Show first 5
                content += f"  {step.number}. {step.action}\n"
            if len(plan.steps) > 5:
                content += f"  ... and {len(plan.steps) - 5} more steps\n"

        self.console.print(Panel(content.strip(), title="Initial Plan", border_style="cyan"))

    def _display_critique(self, critique: Critique) -> None:
        """Display critique results."""
        content = f"**Confidence**: {critique.confidence_score:.0%}\n"

        if critique.strengths:
            content += "\n**Strengths**:\n"
            for s in critique.strengths[:3]:
                content += f"  ✓ {s}\n"

        if critique.weaknesses:
            content += "\n**Weaknesses**:\n"
            for w in critique.weaknesses[:3]:
                content += f"  ✗ {w}\n"

        if critique.improvements:
            content += "\n**Improvements**:\n"
            for i in critique.improvements[:3]:
                content += f"  → {i}\n"

        self.console.print(Panel(content.strip(), title="Self-Critique", border_style="red"))

    def _display_refined_plan(self, refined: RefinedPlan) -> None:
        """Display refined plan."""
        content = f"**Summary**: {refined.final_summary}\n"
        content += f"**Confidence**: {refined.confidence_score:.0%}\n"

        if refined.refinements_made:
            content += "\n**Refinements**:\n"
            for r in refined.refinements_made[:3]:
                content += f"  ✓ {r}\n"

        if refined.final_steps:
            content += "\n**Final Steps**:\n"
            for step in refined.final_steps[:5]:
                content += f"  {step.number}. {step.action}\n"
            if len(refined.final_steps) > 5:
                content += f"  ... and {len(refined.final_steps) - 5} more steps\n"

        self.console.print(Panel(content.strip(), title="Refined Plan", border_style="green"))

    def _display_verification(self, verification: Verification) -> None:
        """Display verification results."""
        status = "✓ Ready" if verification.ready_to_execute else "✗ Not Ready"
        status_color = "green" if verification.ready_to_execute else "red"

        content = f"**Status**: [{status_color}]{status}[/{status_color}]\n"
        content += f"**Confidence**: {verification.final_confidence:.0%}\n"

        if verification.requirements_met:
            content += "\n**Requirements Met**:\n"
            for r in verification.requirements_met[:4]:
                content += f"  ✓ {r}\n"
            if len(verification.requirements_met) > 4:
                content += f"  ... and {len(verification.requirements_met) - 4} more\n"

        if verification.requirements_missing:
            content += "\n**Requirements Missing**:\n"
            for r in verification.requirements_missing[:3]:
                content += f"  ⚠ {r}\n"

        if verification.edge_cases_missing:
            content += "\n**Edge Cases to Consider**:\n"
            for e in verification.edge_cases_missing[:3]:
                content += f"  → {e}\n"

        if verification.blocking_issues:
            content += "\n**Blocking Issues**:\n"
            for b in verification.blocking_issues:
                content += f"  ✗ {b}\n"

        border_color = "green" if verification.ready_to_execute else "yellow"
        self.console.print(Panel(content.strip(), title="Verification", border_style=border_color))
