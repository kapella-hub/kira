"""Tests for PlannerExecutor - board plan decomposition."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from kira.worker.config import WorkerConfig
from kira.worker.executors.planner import PlannerExecutor, PIPELINE_COLUMNS


@pytest.fixture
def config():
    return WorkerConfig(kiro_timeout=10)


@pytest.fixture
def mock_server():
    server = AsyncMock()
    server.report_progress.return_value = {"status": "ok"}
    server.complete_task.return_value = {"status": "completed"}
    server.fail_task.return_value = {"status": "failed"}
    server.create_card.return_value = {"id": "card-new"}
    server.create_column.return_value = {"id": "col-new", "name": "Test"}
    server.update_board.return_value = {"id": "board-1"}
    server.update_column.return_value = {"id": "col-new"}
    return server


@pytest.fixture
def mock_kira_core():
    """Mock kira.core.client and kira.core.models for planner executor tests."""
    mock_client_mod = MagicMock()
    mock_models_mod = MagicMock()

    saved = {}
    modules = {
        "kira.core": MagicMock(),
        "kira.core.client": mock_client_mod,
        "kira.core.models": mock_models_mod,
    }

    for name, mod in modules.items():
        if name in sys.modules:
            saved[name] = sys.modules[name]
        sys.modules[name] = mod

    yield {"client_module": mock_client_mod, "models_module": mock_models_mod}

    for name in modules:
        if name in saved:
            sys.modules[name] = saved[name]
        else:
            sys.modules.pop(name, None)


def _make_fake_kira_client(output: str):
    """Create a mock KiraClient that yields the output as a single chunk."""
    mock_client = MagicMock()

    async def fake_run(prompt, **kwargs):
        yield output

    mock_client.run = fake_run
    return mock_client


SAMPLE_PLAN = {
    "board_name": "User API",
    "board_description": "REST API for user management",
    "plan": (
        "We will build a REST API for user management using FastAPI and SQLite. "
        "The API will support CRUD operations on users with proper validation. "
        "We'll start with the database schema, then implement endpoints, "
        "add authentication, and finish with testing."
    ),
    "cards": [
        {
            "title": "Set up database schema",
            "description": "Create users table with id, email, name",
            "priority": "high",
            "labels": ["backend", "database"],
        },
        {
            "title": "Implement GET /users endpoint",
            "description": "List all users with pagination",
            "priority": "medium",
            "labels": ["backend", "api"],
        },
    ],
}


# --- Parse Plan Tests ---


class TestParsePlanValidJson:
    def test_parses_raw_json(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        raw = json.dumps(SAMPLE_PLAN)
        result = executor._parse_plan(raw)
        assert result["board_name"] == "User API"
        assert len(result["cards"]) == 2

    def test_parses_json_from_markdown_code_block(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        markdown_output = f"Here is the plan:\n\n```json\n{json.dumps(SAMPLE_PLAN)}\n```\n\nLet me know if you want changes."
        result = executor._parse_plan(markdown_output)
        assert result["board_name"] == "User API"
        assert len(result["cards"]) == 2
        assert result["plan"].startswith("We will build")

    def test_parses_json_from_plain_code_block(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        markdown_output = f"```\n{json.dumps(SAMPLE_PLAN)}\n```"
        result = executor._parse_plan(markdown_output)
        assert result["board_name"] == "User API"


class TestParsePlanInvalidJson:
    def test_raises_on_no_json(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        with pytest.raises(ValueError, match="Could not parse"):
            executor._parse_plan("This is just text with no JSON.")

    def test_raises_on_json_without_cards(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        with pytest.raises(ValueError, match="Could not parse"):
            executor._parse_plan('{"name": "not a plan"}')

    def test_raises_on_malformed_json(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        with pytest.raises(ValueError, match="Could not parse"):
            executor._parse_plan('```json\n{"cards": [broken\n```')


# --- Build Plan Prompt Tests ---


class TestBuildPlanPrompt:
    def test_includes_user_request(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        prompt = executor._build_plan_prompt("Build a REST API for user management")
        assert "Build a REST API for user management" in prompt

    def test_includes_json_structure_instructions(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        prompt = executor._build_plan_prompt("any request")
        assert '"cards"' in prompt
        assert '"plan"' in prompt
        assert "board_name" in prompt

    def test_includes_rules(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        prompt = executor._build_plan_prompt("any request")
        assert "Plan" in prompt
        assert "priority" in prompt
        assert "Architect" in prompt

    def test_asks_for_plan_summary(self, config, mock_server):
        executor = PlannerExecutor(config, mock_server, "w-1")
        prompt = executor._build_plan_prompt("any request")
        assert "high-level plan" in prompt.lower()
        assert "acceptance criteria" in prompt.lower()


# --- Pipeline Columns ---


class TestPipelineColumns:
    def test_standard_pipeline_has_five_columns(self):
        assert len(PIPELINE_COLUMNS) == 5

    def test_first_column_is_plan(self):
        assert PIPELINE_COLUMNS[0]["name"] == "Plan"
        assert PIPELINE_COLUMNS[0]["auto_run"] is False

    def test_last_column_is_done(self):
        assert PIPELINE_COLUMNS[-1]["name"] == "Done"
        assert PIPELINE_COLUMNS[-1]["auto_run"] is False

    def test_automation_columns_have_agents(self):
        auto_cols = [c for c in PIPELINE_COLUMNS if c["auto_run"]]
        assert len(auto_cols) == 3
        agent_types = {c["agent_type"] for c in auto_cols}
        assert agent_types == {"architect", "coder", "reviewer"}


# --- Create Board Structure Tests ---


class TestCreateBoardStructure:
    @pytest.mark.asyncio
    async def test_creates_standard_pipeline_columns(self, config, mock_server):
        """Should always create the 5 standard pipeline columns."""
        col_ids = iter(["col-plan", "col-arch", "col-code", "col-review", "col-done"])

        async def fake_create_column(board_id, data):
            col_id = next(col_ids)
            return {"id": col_id, "name": data["name"]}

        mock_server.create_column = AsyncMock(side_effect=fake_create_column)

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", SAMPLE_PLAN)

        # Should create exactly 5 columns (standard pipeline)
        assert mock_server.create_column.call_count == 5

        # Verify column names
        col_names = [
            call.args[1]["name"]
            for call in mock_server.create_column.call_args_list
        ]
        assert col_names == ["Plan", "Architect", "Code", "Review", "Done"]

    @pytest.mark.asyncio
    async def test_creates_plan_summary_card_plus_task_cards(self, config, mock_server):
        """Plan summary card + task cards should all go into the Plan column."""
        col_ids = iter(["col-plan", "col-arch", "col-code", "col-review", "col-done"])

        async def fake_create_column(board_id, data):
            col_id = next(col_ids)
            return {"id": col_id, "name": data["name"]}

        mock_server.create_column = AsyncMock(side_effect=fake_create_column)

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", SAMPLE_PLAN)

        # 1 plan summary card + 2 task cards = 3
        assert mock_server.create_card.call_count == 3

        # First card should be the plan summary
        plan_card_call = mock_server.create_card.call_args_list[0]
        assert plan_card_call.kwargs["column_id"] == "col-plan"
        assert plan_card_call.kwargs["title"] == "Project Plan"
        assert plan_card_call.kwargs["priority"] == "critical"
        assert "FastAPI" in plan_card_call.kwargs["description"]

        # Task cards should also be in Plan column
        for call in mock_server.create_card.call_args_list[1:]:
            assert call.kwargs["column_id"] == "col-plan"

    @pytest.mark.asyncio
    async def test_wires_automation_routing(self, config, mock_server):
        """Auto-run columns should route success→next, failure→Plan."""
        col_ids = iter(["col-plan", "col-arch", "col-code", "col-review", "col-done"])

        async def fake_create_column(board_id, data):
            col_id = next(col_ids)
            return {"id": col_id, "name": data["name"]}

        mock_server.create_column = AsyncMock(side_effect=fake_create_column)

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", SAMPLE_PLAN)

        # 3 auto_run columns should have routing set
        update_calls = mock_server.update_column.call_args_list
        assert len(update_calls) == 3

        # Architect → Code on success, Plan on failure
        arch_call = update_calls[0]
        assert arch_call.args[0] == "col-arch"
        assert arch_call.args[1]["on_success_column_id"] == "col-code"
        assert arch_call.args[1]["on_failure_column_id"] == "col-plan"

        # Code → Review on success, Plan on failure
        code_call = update_calls[1]
        assert code_call.args[0] == "col-code"
        assert code_call.args[1]["on_success_column_id"] == "col-review"
        assert code_call.args[1]["on_failure_column_id"] == "col-plan"

        # Review → Done on success, Plan on failure
        review_call = update_calls[2]
        assert review_call.args[0] == "col-review"
        assert review_call.args[1]["on_success_column_id"] == "col-done"
        assert review_call.args[1]["on_failure_column_id"] == "col-plan"

    @pytest.mark.asyncio
    async def test_updates_board_name_and_description(self, config, mock_server):
        col_ids = iter(["col-plan", "col-arch", "col-code", "col-review", "col-done"])

        async def fake_create_column(board_id, data):
            return {"id": next(col_ids), "name": data["name"]}

        mock_server.create_column = AsyncMock(side_effect=fake_create_column)

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", SAMPLE_PLAN)

        mock_server.update_board.assert_called_once_with(
            "board-1",
            {"name": "User API", "description": "REST API for user management"},
        )

    @pytest.mark.asyncio
    async def test_skips_board_update_when_no_name_or_description(self, config, mock_server):
        plan = {"cards": []}

        mock_server.create_column = AsyncMock(
            return_value={"id": "col-x", "name": "X"}
        )

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", plan)

        mock_server.update_board.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_plan_card_when_no_plan_text(self, config, mock_server):
        """If plan text is empty, only task cards should be created."""
        plan = {
            "cards": [
                {"title": "Task 1", "description": "Do task 1", "priority": "high", "labels": []},
            ],
        }

        col_ids = iter(["col-plan", "col-arch", "col-code", "col-review", "col-done"])
        mock_server.create_column = AsyncMock(
            side_effect=lambda bid, data: {"id": next(col_ids), "name": data["name"]}
        )

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor._create_board_structure("board-1", plan)

        # Only 1 task card, no plan summary card
        assert mock_server.create_card.call_count == 1
        assert mock_server.create_card.call_args.kwargs["title"] == "Task 1"


# --- Full Execution Tests ---


class TestPlannerExecutorHappyPath:
    @pytest.mark.asyncio
    async def test_full_execution(self, config, mock_server, mock_kira_core):
        """End-to-end: AI returns valid plan, columns and cards are created."""
        task = {
            "id": "t-plan",
            "board_id": "board-1",
            "task_type": "board_plan",
            "agent_model": "smart",
            "prompt_text": "Build a REST API for user management",
        }

        ai_output = f"Here is the plan:\n```json\n{json.dumps(SAMPLE_PLAN)}\n```"
        mock_client = _make_fake_kira_client(ai_output)
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        # Should have reported progress
        assert mock_server.report_progress.call_count >= 1

        # Should have completed
        mock_server.complete_task.assert_called_once()
        complete_kwargs = mock_server.complete_task.call_args.kwargs
        assert "2 task cards" in complete_kwargs["output_text"]

    @pytest.mark.asyncio
    async def test_board_plan_reports_five_progress_phases(
        self, config, mock_server, mock_kira_core
    ):
        """board_plan should emit 5 structured progress steps."""
        task = {
            "id": "t-phases",
            "board_id": "board-1",
            "task_type": "board_plan",
            "agent_model": "smart",
            "prompt_text": "Build something",
        }

        ai_output = f"```json\n{json.dumps(SAMPLE_PLAN)}\n```"
        mock_client = _make_fake_kira_client(ai_output)
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        col_ids = iter(
            ["col-plan", "col-arch", "col-code", "col-review", "col-done"]
        )
        mock_server.create_column = AsyncMock(
            side_effect=lambda bid, data: {
                "id": next(col_ids), "name": data["name"],
            }
        )

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        calls = mock_server.report_progress.call_args_list
        assert len(calls) == 5

        # Verify each call has step/total_steps/phase kwargs
        phases_seen = []
        for i, call in enumerate(calls):
            kwargs = call.kwargs
            assert kwargs["step"] == i + 1
            assert kwargs["total_steps"] == 5
            assert kwargs["phase"] is not None
            phases_seen.append(kwargs["phase"])

        assert phases_seen == [
            "analyzing", "thinking", "structuring",
            "creating", "wiring",
        ]


class TestCardGenProgressPhases:
    @pytest.mark.asyncio
    async def test_card_gen_reports_three_progress_phases(
        self, config, mock_server, mock_kira_core
    ):
        """card_gen should emit 3 structured progress steps."""
        cards_output = {
            "cards": [
                {
                    "title": "Task A",
                    "description": "Do A",
                    "priority": "high",
                    "labels": ["backend"],
                },
            ],
        }
        task = {
            "id": "t-cg",
            "board_id": "board-1",
            "task_type": "card_gen",
            "agent_model": "smart",
            "prompt_text": "Generate tasks",
            "payload_json": json.dumps(
                {"target_column_id": "col-plan"}
            ),
        }

        ai_output = f"```json\n{json.dumps(cards_output)}\n```"
        mock_client = _make_fake_kira_client(ai_output)
        mock_kira_core["client_module"].KiraClient.return_value = (
            mock_client
        )
        mock_kira_core["models_module"].resolve_model.return_value = (
            "claude-sonnet-4"
        )

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        calls = mock_server.report_progress.call_args_list
        assert len(calls) == 3

        phases_seen = []
        for i, call in enumerate(calls):
            kwargs = call.kwargs
            assert kwargs["step"] == i + 1
            assert kwargs["total_steps"] == 3
            phases_seen.append(kwargs["phase"])

        assert phases_seen == ["analyzing", "thinking", "creating"]

        # Verify completion
        mock_server.complete_task.assert_called_once()


class TestPlannerExecutorEmptyPrompt:
    @pytest.mark.asyncio
    async def test_fails_with_empty_prompt(self, config, mock_server):
        task = {
            "id": "t-empty",
            "board_id": "board-1",
            "task_type": "board_plan",
            "prompt_text": "",
        }

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "no prompt_text" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()


class TestPlannerExecutorAiFailure:
    @pytest.mark.asyncio
    async def test_fails_when_ai_returns_invalid_json(self, config, mock_server, mock_kira_core):
        task = {
            "id": "t-bad-ai",
            "board_id": "board-1",
            "task_type": "board_plan",
            "agent_model": "smart",
            "prompt_text": "Do something",
        }

        mock_client = _make_fake_kira_client("Sorry, I can't create a plan right now.")
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "parse" in mock_server.fail_task.call_args.kwargs["error_summary"].lower()

    @pytest.mark.asyncio
    async def test_fails_when_kiro_raises(self, config, mock_server, mock_kira_core):
        task = {
            "id": "t-crash",
            "board_id": "board-1",
            "task_type": "board_plan",
            "agent_model": "smart",
            "prompt_text": "Do something",
        }

        mock_client = MagicMock()

        async def failing_run(prompt, **kwargs):
            raise RuntimeError("kiro-cli crashed")
            yield  # Make it a generator

        mock_client.run = failing_run
        mock_kira_core["client_module"].KiraClient.return_value = mock_client
        mock_kira_core["models_module"].resolve_model.return_value = "claude-sonnet-4"

        executor = PlannerExecutor(config, mock_server, "w-1")
        await executor.execute(task)

        mock_server.fail_task.assert_called_once()
        assert "crashed" in mock_server.fail_task.call_args.kwargs["error_summary"]
