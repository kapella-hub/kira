"""Tests for worker and task services."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

# Schema path
SCHEMA_PATH = Path(__file__).parent.parent / "src" / "kira" / "web" / "db" / "schema.sql"


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create an in-memory database with the full schema."""
    db_path = str(tmp_path / "test.db")
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")

    schema_sql = SCHEMA_PATH.read_text()
    await conn.executescript(schema_sql)
    await conn.commit()

    # Create a test user
    await conn.execute(
        "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
        ("user1", "testuser", "Test User"),
    )
    # Create a second user
    await conn.execute(
        "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
        ("user2", "otheruser", "Other User"),
    )
    # Create a board
    await conn.execute(
        "INSERT INTO boards (id, name, owner_id) VALUES (?, ?, ?)",
        ("board1", "Test Board", "user1"),
    )
    # Add user1 as board member
    await conn.execute(
        "INSERT INTO board_members (board_id, user_id, role) VALUES (?, ?, ?)",
        ("board1", "user1", "owner"),
    )
    # Create a column
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col1", "board1", "Todo", 0),
    )
    # Create an auto_run column
    await conn.execute(
        """INSERT INTO columns (id, board_id, name, position, agent_type, auto_run,
           on_success_column_id, on_failure_column_id, max_loop_count, prompt_template)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("col_auto", "board1", "Code", 1, "coder", 1, "col_review", "col1", 3, "Code this: {card_title}"),
    )
    # Create a review column
    await conn.execute(
        """INSERT INTO columns (id, board_id, name, position, agent_type, auto_run,
           on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("col_review", "board1", "Review", 2, "reviewer", 1, "col_done", "col_auto", 3),
    )
    # Create a done column
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col_done", "board1", "Done", 3),
    )
    # Create a card
    await conn.execute(
        """INSERT INTO cards (id, column_id, board_id, title, description, position, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("card1", "col1", "board1", "Test Card", "Build a REST API", 0, "user1"),
    )
    await conn.commit()

    yield conn

    await conn.close()


# --- Worker Service Tests ---


class TestWorkerService:
    @pytest.mark.asyncio
    async def test_register_worker(self, db):
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1", hostname="my-macbook", worker_version="0.3.0")
        assert worker["user_id"] == "user1"
        assert worker["hostname"] == "my-macbook"
        assert worker["status"] == "online"
        assert worker["worker_version"] == "0.3.0"

    @pytest.mark.asyncio
    async def test_register_worker_upsert(self, db):
        """Re-registering the same user updates the existing worker."""
        from kira.web.workers.service import register_worker

        w1 = await register_worker(db, "user1", hostname="old-host")
        w2 = await register_worker(db, "user1", hostname="new-host")
        assert w1["id"] == w2["id"]  # Same worker row
        assert w2["hostname"] == "new-host"

    @pytest.mark.asyncio
    async def test_heartbeat(self, db):
        from kira.web.workers.service import heartbeat, register_worker

        worker = await register_worker(db, "user1")
        result = await heartbeat(db, worker["id"], "user1")
        assert result["status"] == "ok"
        assert result["cancel_task_ids"] == []

    @pytest.mark.asyncio
    async def test_heartbeat_returns_cancelled_tasks(self, db):
        from kira.web.tasks.service import cancel_task, create_task
        from kira.web.workers.service import heartbeat, register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
        )
        # Cancel the task
        await cancel_task(db, task["id"])

        # Heartbeat with the cancelled task ID
        result = await heartbeat(db, worker["id"], "user1", running_task_ids=[task["id"]])
        assert task["id"] in result["cancel_task_ids"]

    @pytest.mark.asyncio
    async def test_get_workers(self, db):
        from kira.web.workers.service import get_workers, register_worker

        await register_worker(db, "user1")
        workers = await get_workers(db)
        assert len(workers) == 1

    @pytest.mark.asyncio
    async def test_get_worker_for_user(self, db):
        from kira.web.workers.service import get_worker_for_user, register_worker

        assert await get_worker_for_user(db, "user1") is None
        await register_worker(db, "user1")
        worker = await get_worker_for_user(db, "user1")
        assert worker is not None
        assert worker["user_id"] == "user1"

    @pytest.mark.asyncio
    async def test_mark_stale_workers(self, db):
        from kira.web.workers.service import mark_stale_workers, register_worker

        await register_worker(db, "user1")
        # Force last_heartbeat to be old
        await db.execute(
            "UPDATE workers SET last_heartbeat = datetime('now', '-100 seconds') WHERE user_id = ?",
            ("user1",),
        )
        await db.commit()

        changed = await mark_stale_workers(db)
        assert changed >= 1

        cursor = await db.execute("SELECT status FROM workers WHERE user_id = ?", ("user1",))
        row = await cursor.fetchone()
        assert row["status"] == "stale"

    @pytest.mark.asyncio
    async def test_mark_offline_workers_fail_tasks(self, db):
        from kira.web.tasks.service import claim_task, create_task
        from kira.web.workers.service import mark_stale_workers, register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
        )
        await claim_task(db, task["id"], worker["id"])

        # Force last_heartbeat to be very old (offline threshold)
        await db.execute(
            "UPDATE workers SET last_heartbeat = datetime('now', '-400 seconds') WHERE user_id = ?",
            ("user1",),
        )
        await db.commit()

        await mark_stale_workers(db)

        # Check task is failed
        cursor = await db.execute("SELECT status FROM tasks WHERE id = ?", (task["id"],))
        row = await cursor.fetchone()
        assert row["status"] == "failed"


# --- Task Service Tests ---


class TestTaskService:
    @pytest.mark.asyncio
    async def test_create_task(self, db):
        from kira.web.tasks.service import create_task

        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
            agent_type="coder", agent_model="smart",
        )
        assert task["status"] == "pending"
        assert task["task_type"] == "agent_run"
        assert task["agent_type"] == "coder"

    @pytest.mark.asyncio
    async def test_create_task_updates_card_agent_status(self, db):
        from kira.web.tasks.service import create_task

        await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1",
        )

        cursor = await db.execute("SELECT agent_status FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["agent_status"] == "pending"

    @pytest.mark.asyncio
    async def test_poll_tasks(self, db):
        from kira.web.tasks.service import create_task, poll_tasks

        await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
        )
        tasks = await poll_tasks(db, "user1")
        assert len(tasks) == 1

        # Different user sees nothing
        tasks = await poll_tasks(db, "user2")
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_poll_tasks_priority_ordering(self, db):
        from kira.web.tasks.service import create_task, poll_tasks

        t_low = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1", priority=0,
        )
        t_high = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1", priority=10,
        )

        tasks = await poll_tasks(db, "user1", limit=2)
        assert tasks[0]["id"] == t_high["id"]  # Higher priority first

    @pytest.mark.asyncio
    async def test_claim_task(self, db):
        from kira.web.tasks.service import claim_task, create_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
        )

        claimed = await claim_task(db, task["id"], worker["id"])
        assert claimed is not None
        assert claimed["status"] == "claimed"

    @pytest.mark.asyncio
    async def test_claim_task_already_claimed(self, db):
        from kira.web.tasks.service import claim_task, create_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1", assigned_to="user1",
        )

        await claim_task(db, task["id"], worker["id"])
        # Second claim should fail
        result = await claim_task(db, task["id"], worker["id"])
        assert result is None

    @pytest.mark.asyncio
    async def test_update_progress(self, db):
        from kira.web.tasks.service import claim_task, create_task, update_progress
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
        )
        await claim_task(db, task["id"], worker["id"])

        updated = await update_progress(db, task["id"], "Phase 1/3")
        assert updated["status"] == "running"
        assert updated["started_at"] is not None

        # Card should be running
        cursor = await db.execute("SELECT agent_status FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["agent_status"] == "running"

    @pytest.mark.asyncio
    async def test_complete_task(self, db):
        from kira.web.tasks.service import claim_task, complete_task, create_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
        )
        await claim_task(db, task["id"], worker["id"])

        result = await complete_task(db, task["id"], output_text="Done!")
        assert result["status"] == "completed"

        # Check comment was created
        cursor = await db.execute(
            "SELECT * FROM card_comments WHERE card_id = ? AND is_agent_output = 1",
            ("card1",),
        )
        comment = await cursor.fetchone()
        assert comment is not None
        assert comment["content"] == "Done!"

        # Card status should be completed
        cursor = await db.execute("SELECT agent_status FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["agent_status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_task_moves_card_to_target(self, db):
        from kira.web.tasks.service import claim_task, complete_task, create_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
            target_column_id="col_done",
        )
        await claim_task(db, task["id"], worker["id"])

        result = await complete_task(db, task["id"], output_text="All done")
        assert result.get("next_action") is not None
        assert result["next_action"]["to_column_id"] == "col_done"

        # Card should be in col_done
        cursor = await db.execute("SELECT column_id FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["column_id"] == "col_done"

    @pytest.mark.asyncio
    async def test_complete_task_reviewer_rejection(self, db):
        from kira.web.tasks.service import claim_task, complete_task, create_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
            agent_type="reviewer",
            target_column_id="col_done",
            failure_column_id="col1",
        )
        await claim_task(db, task["id"], worker["id"])

        result = await complete_task(
            db, task["id"], output_text="REJECTED: code quality issues"
        )
        assert result["status"] == "failed"

        # Card should move to failure column, not target
        cursor = await db.execute("SELECT column_id FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["column_id"] == "col1"

    @pytest.mark.asyncio
    async def test_fail_task(self, db):
        from kira.web.tasks.service import claim_task, create_task, fail_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
        )
        await claim_task(db, task["id"], worker["id"])

        result = await fail_task(db, task["id"], error_summary="kiro-cli timeout")
        assert result["status"] == "failed"

        cursor = await db.execute("SELECT agent_status FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["agent_status"] == "failed"

    @pytest.mark.asyncio
    async def test_fail_task_moves_card_to_failure_column(self, db):
        from kira.web.tasks.service import claim_task, create_task, fail_task
        from kira.web.workers.service import register_worker

        worker = await register_worker(db, "user1")
        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1", assigned_to="user1",
            failure_column_id="col_done",
        )
        await claim_task(db, task["id"], worker["id"])

        result = await fail_task(db, task["id"], error_summary="error")
        assert result["next_action"]["to_column_id"] == "col_done"
        assert result["next_action"]["automation_triggered"] is False

    @pytest.mark.asyncio
    async def test_cancel_task(self, db):
        from kira.web.tasks.service import cancel_task, create_task

        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1",
        )
        result = await cancel_task(db, task["id"])
        assert result["status"] == "cancelled"

        # Card agent_status should be cleared
        cursor = await db.execute("SELECT agent_status FROM cards WHERE id = ?", ("card1",))
        row = await cursor.fetchone()
        assert row["agent_status"] == ""

    @pytest.mark.asyncio
    async def test_cancel_completed_task_raises(self, db):
        from kira.web.tasks.service import cancel_task, complete_task, create_task

        task = await create_task(
            db, task_type="agent_run", board_id="board1",
            created_by="user1",
        )
        await complete_task(db, task["id"])

        with pytest.raises(ValueError, match="Cannot cancel"):
            await cancel_task(db, task["id"])

    @pytest.mark.asyncio
    async def test_get_tasks_with_filters(self, db):
        from kira.web.tasks.service import create_task, get_tasks

        await create_task(
            db, task_type="agent_run", board_id="board1",
            card_id="card1", created_by="user1",
        )
        await create_task(
            db, task_type="jira_import", board_id="board1",
            created_by="user1",
        )

        all_tasks = await get_tasks(db, board_id="board1")
        assert len(all_tasks) == 2

        card_tasks = await get_tasks(db, card_id="card1")
        assert len(card_tasks) == 1

        pending = await get_tasks(db, status="pending")
        assert len(pending) == 2


# --- Automation Tests ---


class TestAutomation:
    @pytest.mark.asyncio
    async def test_maybe_trigger_no_auto_run(self, db):
        from kira.web.automation.trigger import maybe_trigger

        card = {"id": "card1", "board_id": "board1", "title": "Test", "assignee_id": None}
        column = {"id": "col1", "auto_run": False, "agent_type": "coder"}
        result = await maybe_trigger(db, card, column, "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_maybe_trigger_no_agent_type(self, db):
        from kira.web.automation.trigger import maybe_trigger

        card = {"id": "card1", "board_id": "board1", "title": "Test", "assignee_id": None}
        column = {"id": "col1", "auto_run": True, "agent_type": ""}
        result = await maybe_trigger(db, card, column, "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_maybe_trigger_creates_task(self, db):
        from kira.web.automation.trigger import maybe_trigger

        card = {
            "id": "card1", "board_id": "board1", "title": "Test Card",
            "description": "Build API", "assignee_id": None,
        }
        column = {
            "id": "col_auto", "auto_run": True, "agent_type": "coder",
            "agent_skill": "", "agent_model": "smart",
            "on_success_column_id": "col_review", "on_failure_column_id": "col1",
            "max_loop_count": 3, "prompt_template": "Code this: {card_title}",
        }

        task = await maybe_trigger(db, card, column, "user1")
        assert task is not None
        assert task["task_type"] == "agent_run"
        assert task["agent_type"] == "coder"
        assert task["target_column_id"] == "col_review"
        assert task["prompt_text"] == "Code this: Test Card"

    @pytest.mark.asyncio
    async def test_maybe_trigger_circuit_breaker(self, db):
        from kira.web.automation.trigger import maybe_trigger
        from kira.web.tasks.service import create_task

        card = {
            "id": "card1", "board_id": "board1", "title": "Test",
            "assignee_id": None,
        }
        column = {
            "id": "col_auto", "auto_run": True, "agent_type": "coder",
            "max_loop_count": 2, "prompt_template": "",
        }

        # Create 2 existing tasks for this card+column
        for _ in range(2):
            await create_task(
                db, task_type="agent_run", board_id="board1",
                card_id="card1", created_by="user1",
                source_column_id="col_auto",
            )

        # Should be blocked by circuit breaker
        result = await maybe_trigger(db, card, column, "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_maybe_trigger_assigns_to_card_assignee(self, db):
        from kira.web.automation.trigger import maybe_trigger

        card = {
            "id": "card1", "board_id": "board1", "title": "Test",
            "assignee_id": "user2",
        }
        column = {
            "id": "col_auto", "auto_run": True, "agent_type": "coder",
            "max_loop_count": 3, "prompt_template": "",
        }

        task = await maybe_trigger(db, card, column, "user1")
        assert task["assigned_to"] == "user2"


# --- Prompt Rendering Tests ---


class TestPromptRendering:
    def test_render_default_template(self):
        from kira.web.automation.prompt import render_prompt

        card = {"title": "My Card", "description": "Do the thing", "labels": "[]", "priority": "high"}
        column = {"name": "Code", "agent_type": "coder"}

        result = render_prompt("", card, column)
        assert "My Card" in result
        assert "Do the thing" in result
        assert "coder" in result

    def test_render_custom_template(self):
        from kira.web.automation.prompt import render_prompt

        card = {"title": "Build API", "description": "REST API"}
        column = {"agent_type": "architect"}

        result = render_prompt("Design: {card_title} - {agent_type}", card, column)
        assert result == "Design: Build API - architect"

    def test_render_missing_variables_left_as_is(self):
        from kira.web.automation.prompt import render_prompt

        result = render_prompt("{unknown_var}", {}, {})
        assert result == "{unknown_var}"


# --- Integration: move_card triggers automation ---


class TestMoveCardAutomation:
    @pytest.mark.asyncio
    async def test_move_card_to_auto_run_column_triggers_task(self, db):
        from kira.web.cards.service import move_card
        from kira.web.tasks.service import get_tasks

        # Move card from col1 to col_auto (which has auto_run=True)
        await move_card(db, "card1", "col_auto", 0, user_id="user1")

        # Should have created a task
        tasks = await get_tasks(db, card_id="card1")
        assert len(tasks) == 1
        assert tasks[0]["agent_type"] == "coder"
        assert tasks[0]["source_column_id"] == "col_auto"

    @pytest.mark.asyncio
    async def test_move_card_skip_automation(self, db):
        from kira.web.cards.service import move_card
        from kira.web.tasks.service import get_tasks

        await move_card(db, "card1", "col_auto", 0, user_id="user1", skip_automation=True)

        tasks = await get_tasks(db, card_id="card1")
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_move_card_same_column_no_automation(self, db):
        from kira.web.cards.service import move_card
        from kira.web.tasks.service import get_tasks

        # Move within same column (reorder) should not trigger
        await move_card(db, "card1", "col1", 0, user_id="user1")

        tasks = await get_tasks(db, card_id="card1")
        assert len(tasks) == 0
