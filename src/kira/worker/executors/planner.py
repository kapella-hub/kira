"""Planner executor -- decomposes a natural language request into a kanban board.

This executor handles two task types:

  'board_plan' -- full board creation:
    1. Sends the user's prompt to an AI agent to produce a plan + task cards.
    2. Parses the JSON plan from the AI output.
    3. Creates standard pipeline columns (Plan -> Architect -> Code -> Review -> Done).
    4. Places the plan summary and task cards into the Plan column.
    5. Wires up automation routing between columns.

  'card_gen' -- card-only generation on an existing board:
    1. Sends the user's prompt to an AI agent to produce task cards.
    2. Parses the JSON card list from the AI output.
    3. Creates cards in the specified target column (no new columns).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..client import ServerClient, ServerError
from ..config import WorkerConfig

logger = logging.getLogger(__name__)

# Standard pipeline columns created for every board plan.
# The AI does not control column structure -- only cards.
PIPELINE_COLUMNS = [
    {"name": "Plan", "color": "#6B7280", "agent_type": "", "auto_run": False},
    {"name": "Architect", "color": "#8B5CF6", "agent_type": "architect", "auto_run": True},
    {"name": "Code", "color": "#3B82F6", "agent_type": "coder", "auto_run": True},
    {"name": "Review", "color": "#F59E0B", "agent_type": "reviewer", "auto_run": True},
    {"name": "Done", "color": "#10B981", "agent_type": "", "auto_run": False},
]


class PlannerExecutor:
    """Executes board_plan and card_gen tasks via AI agent."""

    def __init__(self, config: WorkerConfig, server: ServerClient, worker_id: str):
        self.config = config
        self.server = server
        self.worker_id = worker_id

    async def execute(self, task: dict[str, Any], working_dir: Path | None = None) -> None:
        """Route to the appropriate execution method based on task_type."""
        self._working_dir = working_dir
        task_type = task.get("task_type", "board_plan")

        if task_type == "card_gen":
            await self._execute_card_gen(task)
        else:
            await self._execute_board_plan(task)

    async def _execute_board_plan(self, task: dict[str, Any]) -> None:
        """Decompose a prompt into a plan and create the board structure.

        Flow:
          1. AI produces a plan summary + task cards (JSON).
          2. Executor creates standard pipeline columns.
          3. Plan summary card + task cards go into the Plan column.
          4. Automation routing is wired between columns.
        """
        task_id = task["id"]
        board_id = task["board_id"]
        prompt = task.get("prompt_text", "")

        if not prompt:
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary="Task has no prompt_text",
            )
            return

        try:
            # Step 1/5: Analyzing
            await self._report_progress(
                task_id,
                "Analyzing your request...",
                step=1, total_steps=5, phase="analyzing",
            )

            # Step 2/5: AI thinking
            plan_prompt = self._build_plan_prompt(prompt)
            await self._report_progress(
                task_id,
                "AI is creating a project plan...",
                step=2, total_steps=5, phase="thinking",
            )
            output = await self._run_agent(task, plan_prompt)

            # Parse the JSON plan from AI output
            plan = self._parse_plan(output)
            num_cards = len(plan.get("cards", []))

            # Step 3/5: Structuring columns
            await self._report_progress(
                task_id,
                "Setting up board columns...",
                step=3, total_steps=5, phase="structuring",
            )

            # Create columns, cards, and automation with
            # mid-structure progress reports
            await self._create_board_structure(
                board_id, plan, task_id=task_id,
            )

            # Complete task
            await self.server.complete_task(
                task_id,
                self.worker_id,
                output_text=(
                    f"Board plan created: {num_cards} task cards"
                    " in Plan column"
                ),
            )

        except Exception as e:
            error_msg = str(e)
            logger.error("Task %s failed: board_plan, error=%s", task_id, error_msg)
            await self.server.fail_task(
                task_id,
                self.worker_id,
                error_summary=error_msg,
            )

    def _build_plan_prompt(self, prompt: str) -> str:
        """Build the structured prompt for the AI agent.

        The AI is asked to produce a plan summary and task cards only.
        Column structure is handled by the executor.
        """
        return f"""You are a project planning agent. Analyze the following request and create a detailed project plan.

## Request
{prompt}

## Instructions
Create a project plan with a high-level summary and individual task cards.
Output ONLY valid JSON with this exact structure:

```json
{{
  "board_name": "Short descriptive board name",
  "board_description": "One-line description of the project",
  "plan": "A detailed high-level plan describing the overall approach, architecture decisions, key components, dependencies, and implementation strategy. This should be 2-5 paragraphs that give a clear picture of how the project will be built.",
  "cards": [
    {{
      "title": "Short task title",
      "description": "Detailed description of what needs to be done including:\\n- Acceptance criteria\\n- Technical details\\n- Dependencies on other cards",
      "priority": "high",
      "labels": ["backend", "auth"]
    }}
  ]
}}
```

## Rules
- The "plan" field should be a thorough high-level plan (2-5 paragraphs)
- Each card should be a single, well-defined unit of work
- Card descriptions must be detailed enough for an AI coding agent to implement without ambiguity
- Include acceptance criteria in every card description
- Use appropriate labels: "backend", "frontend", "database", "api", "auth", "testing", "infra", "docs"
- Set priority: "critical" for blockers, "high" for core features, "medium" for supporting work, "low" for polish
- Create 5-15 cards depending on project complexity
- Order cards by dependency -- foundational work first, then features that build on it
- Cards will be placed in a Plan column and flow through: Plan → Architect → Code → Review → Done"""

    def _parse_plan(self, output: str) -> dict[str, Any]:
        """Extract and parse JSON plan from AI output.

        Looks for JSON in markdown code blocks or raw JSON.
        Expects a "cards" key in the parsed object.

        Raises:
            ValueError: If no valid JSON plan is found.
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", output, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if "cards" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object in the output
        brace_depth = 0
        start_idx = None
        for i, ch in enumerate(output):
            if ch == "{":
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0 and start_idx is not None:
                    candidate = output[start_idx : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if "cards" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    start_idx = None

        raise ValueError(
            "Could not parse board plan from AI output. No valid JSON with 'cards' key found."
        )

    async def _create_board_structure(
        self,
        board_id: str,
        plan: dict[str, Any],
        *,
        task_id: str | None = None,
    ) -> None:
        """Create standard pipeline columns and place cards in the Plan column.

        When *task_id* is provided, structured progress events are
        emitted between the column-creation, card-creation, and
        automation-wiring phases.
        """
        # Update board name/description
        board_name = plan.get("board_name", "")
        board_desc = plan.get("board_description", "")
        if board_name or board_desc:
            update_data: dict[str, str] = {}
            if board_name:
                update_data["name"] = board_name
            if board_desc:
                update_data["description"] = board_desc
            try:
                await self.server.update_board(board_id, update_data)
            except ServerError as e:
                logger.warning(
                    "Failed to update board name/description: %s",
                    e.message,
                )

        # --- Create standard pipeline columns ---
        created_columns: list[dict[str, Any]] = []
        for col_spec in PIPELINE_COLUMNS:
            try:
                col = await self.server.create_column(
                    board_id,
                    {
                        "name": col_spec["name"],
                        "color": col_spec["color"],
                        "agent_type": col_spec["agent_type"],
                        "auto_run": col_spec["auto_run"],
                    },
                )
                created_columns.append(
                    {"spec": col_spec, "created": col},
                )
            except ServerError as e:
                logger.warning(
                    "Failed to create column '%s': %s",
                    col_spec["name"],
                    e.message,
                )

        plan_col_id = (
            created_columns[0]["created"]["id"]
            if created_columns
            else ""
        )

        # --- Step 4/5: Creating cards ---
        num_cards = len(plan.get("cards", []))
        if task_id:
            await self._report_progress(
                task_id,
                f"Creating {num_cards} task cards...",
                step=4, total_steps=5, phase="creating",
            )

        # Create plan summary card as first card in the Plan column
        plan_text = plan.get("plan", "")
        if plan_text and plan_col_id:
            try:
                await self.server.create_card(
                    column_id=plan_col_id,
                    title="Project Plan",
                    description=plan_text,
                    priority="critical",
                    labels=json.dumps(["plan"]),
                )
            except ServerError as e:
                logger.warning(
                    "Failed to create plan summary card: %s",
                    e.message,
                )

        # Create task cards in the Plan column
        for card_spec in plan.get("cards", []):
            if not plan_col_id:
                break

            labels = card_spec.get("labels", [])
            labels_str = (
                json.dumps(labels)
                if isinstance(labels, list)
                else str(labels)
            )

            try:
                await self.server.create_card(
                    column_id=plan_col_id,
                    title=card_spec.get("title", "Untitled"),
                    description=card_spec.get("description", ""),
                    priority=card_spec.get("priority", "medium"),
                    labels=labels_str,
                )
            except ServerError as e:
                logger.warning(
                    "Failed to create card '%s': %s",
                    card_spec.get("title", "?"),
                    e.message,
                )

        # --- Step 5/5: Wiring automation ---
        if task_id:
            await self._report_progress(
                task_id,
                "Wiring automation between columns...",
                step=5, total_steps=5, phase="wiring",
            )

        for i, col_info in enumerate(created_columns):
            spec = col_info["spec"]
            created = col_info["created"]

            if spec["auto_run"] and spec["agent_type"]:
                success_col_id = ""
                if i + 1 < len(created_columns):
                    success_col_id = (
                        created_columns[i + 1]["created"]["id"]
                    )

                if success_col_id or plan_col_id:
                    try:
                        await self.server.update_column(
                            created["id"],
                            {
                                "on_success_column_id": success_col_id,
                                "on_failure_column_id": plan_col_id,
                            },
                        )
                    except ServerError as e:
                        logger.warning(
                            "Failed to set routing for column '%s': %s",
                            created["id"],
                            e.message,
                        )

    async def _execute_card_gen(self, task: dict[str, Any]) -> None:
        """Generate cards for an existing board without creating columns."""
        task_id = task["id"]
        prompt = task.get("prompt_text", "")

        if not prompt:
            await self.server.fail_task(
                task_id, self.worker_id, error_summary="Task has no prompt_text"
            )
            return

        try:
            # Step 1/3: Analyzing
            await self._report_progress(
                task_id,
                "Analyzing your request...",
                step=1, total_steps=3, phase="analyzing",
            )

            # Get target column from payload
            payload = json.loads(task.get("payload_json", "{}"))
            target_column_id = payload.get("target_column_id", "")

            # Step 2/3: AI thinking
            await self._report_progress(
                task_id,
                "AI is generating task cards...",
                step=2, total_steps=3, phase="thinking",
            )
            card_prompt = self._build_card_gen_prompt(prompt)
            output = await self._run_agent(task, card_prompt)

            # Parse cards from AI output
            cards = self._parse_cards(output)
            num_cards = len(cards)

            # Step 3/3: Creating cards
            await self._report_progress(
                task_id,
                f"Creating {num_cards} cards...",
                step=3, total_steps=3, phase="creating",
            )

            # Create cards in the target column
            for card_spec in cards:
                if not target_column_id:
                    break

                labels = card_spec.get("labels", [])
                labels_str = json.dumps(labels) if isinstance(labels, list) else str(labels)

                try:
                    await self.server.create_card(
                        column_id=target_column_id,
                        title=card_spec.get("title", "Untitled"),
                        description=card_spec.get("description", ""),
                        priority=card_spec.get("priority", "medium"),
                        labels=labels_str,
                    )
                except ServerError as e:
                    logger.warning(
                        "Failed to create card '%s': %s",
                        card_spec.get("title", "?"),
                        e.message,
                    )

            await self.server.complete_task(
                task_id,
                self.worker_id,
                output_text=f"Generated {num_cards} cards",
            )

        except Exception as e:
            error_msg = str(e)
            logger.error("Task %s failed: card_gen, error=%s", task_id, error_msg)
            await self.server.fail_task(task_id, self.worker_id, error_summary=error_msg)

    def _build_card_gen_prompt(self, prompt: str) -> str:
        """Build a prompt for generating cards only (no board structure)."""
        return f"""You are a task planning agent. \
Analyze the following request and create task cards.

## Request
{prompt}

## Instructions
Create task cards for an existing project board.
Output ONLY valid JSON with this exact structure:

```json
{{
  "cards": [
    {{
      "title": "Short task title",
      "description": "Detailed description with acceptance criteria",
      "priority": "high",
      "labels": ["backend", "api"]
    }}
  ]
}}
```

## Rules
- Each card should be a single, well-defined unit of work
- Card descriptions must be detailed enough for an AI agent to implement
- Include acceptance criteria in every card description
- Use labels from: backend, frontend, database, api, auth, testing, infra, docs
- Priority: critical (blockers), high (core), medium (supporting), low (polish)
- Create 3-10 cards depending on complexity
- Order cards by dependency -- foundational work first"""

    def _parse_cards(self, output: str) -> list[dict[str, Any]]:
        """Extract card list from AI output."""
        plan = self._parse_plan(output)
        return plan.get("cards", [])

    async def _run_agent(self, task: dict[str, Any], prompt: str) -> str:
        """Run the AI agent via kiro-cli and collect the full output."""
        from kira.core.client import KiraClient
        from kira.core.models import resolve_model

        model = resolve_model(task.get("agent_model", "smart"))

        client = KiraClient(
            model=model,
            trust_all_tools=False,
            timeout=self.config.kiro_timeout,
            working_dir=self._working_dir,
        )

        chunks: list[str] = []
        async for chunk in client.run(prompt):
            chunks.append(chunk)

        return "".join(chunks)

    async def _report_progress(
        self,
        task_id: str,
        text: str,
        *,
        step: int | None = None,
        total_steps: int | None = None,
        phase: str | None = None,
    ) -> None:
        """Report progress, swallowing errors to avoid interrupting execution."""
        try:
            await self.server.report_progress(
                task_id,
                self.worker_id,
                text,
                step=step,
                total_steps=total_steps,
                phase=phase,
            )
        except ServerError as e:
            logger.debug(
                "Progress report failed for task %s: %s",
                task_id,
                e.message,
            )
