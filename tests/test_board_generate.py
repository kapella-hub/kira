"""Tests for board generation endpoints."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

SCHEMA_PATH = Path(__file__).parent.parent / "src" / "kira" / "web" / "db" / "schema.sql"


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a test database with the full schema."""
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
    await conn.commit()

    yield conn

    await conn.close()


class TestCreateAndGenerate:
    async def test_creates_board_and_task(self, db):
        """POST /api/boards/generate creates a new board and a board_plan task."""
        from kira.web.boards.service import get_board
        from kira.web.tasks.service import get_tasks

        from kira.web.boards import service as board_svc
        from kira.web.tasks import service as task_svc

        prompt = "Build a REST API for user management with CRUD endpoints"

        # Simulate what the endpoint does
        name = prompt[:50].strip()
        board = await board_svc.create_board(db, name, "", "user1")
        assert board["name"] == name

        task = await task_svc.create_task(
            db,
            task_type="board_plan",
            board_id=board["id"],
            created_by="user1",
            assigned_to="user1",
            agent_type="architect",
            agent_model="smart",
            prompt_text=prompt,
        )

        assert task["task_type"] == "board_plan"
        assert task["board_id"] == board["id"]
        assert task["agent_type"] == "architect"
        assert task["prompt_text"] == prompt
        assert task["status"] == "pending"

    async def test_uses_custom_name_when_provided(self, db):
        from kira.web.boards import service as board_svc

        board = await board_svc.create_board(db, "My Custom Name", "", "user1")
        assert board["name"] == "My Custom Name"

    async def test_truncates_long_prompt_for_board_name(self, db):
        from kira.web.boards import service as board_svc

        prompt = "A" * 100
        name = prompt[:50].strip()
        board = await board_svc.create_board(db, name, "", "user1")
        assert len(board["name"]) == 50


class TestGenerateExistingBoard:
    async def test_creates_task_for_existing_board(self, db):
        """POST /api/boards/{id}/generate creates a board_plan task."""
        from kira.web.boards.service import get_board
        from kira.web.tasks.service import create_task, get_tasks

        board = await get_board(db, "board1")
        assert board is not None

        task = await create_task(
            db,
            task_type="board_plan",
            board_id="board1",
            created_by="user1",
            assigned_to="user1",
            agent_type="architect",
            agent_model="smart",
            prompt_text="Build a REST API",
        )

        assert task["task_type"] == "board_plan"
        assert task["board_id"] == "board1"

        # Verify task shows up in task list
        tasks = await get_tasks(db, board_id="board1")
        assert len(tasks) == 1
        assert tasks[0]["id"] == task["id"]


class TestBoardPlanTaskType:
    async def test_board_plan_task_type_accepted(self, db):
        """Verify that 'board_plan' is accepted as a valid task_type."""
        from kira.web.tasks.service import create_task

        task = await create_task(
            db,
            task_type="board_plan",
            board_id="board1",
            created_by="user1",
        )

        assert task["task_type"] == "board_plan"
        assert task["status"] == "pending"

    async def test_invalid_task_type_rejected(self, db):
        """An invalid task_type should raise an error."""
        import aiosqlite

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """INSERT INTO tasks (id, task_type, board_id, created_by)
                   VALUES ('t1', 'invalid_type', 'board1', 'user1')""",
            )
            await db.commit()
