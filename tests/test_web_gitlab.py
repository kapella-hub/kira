"""Tests for GitLab integration -- credentials, link project, push tasks, auto-chain."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from kira.web.tasks.service import complete_task, create_task

# Schema path
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

    # Create test users
    await conn.execute(
        "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
        ("user1", "testuser", "Test User"),
    )
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
    # Create columns
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col1", "board1", "Todo", 0),
    )
    await conn.execute(
        """INSERT INTO columns (id, board_id, name, position, agent_type, auto_run,
           on_success_column_id, on_failure_column_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("col_code", "board1", "Code", 1, "coder", 1, "col_done", "col1"),
    )
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col_done", "board1", "Done", 2),
    )
    # Create a card
    await conn.execute(
        """INSERT INTO cards (id, column_id, board_id, title, description, position, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("card1", "col1", "board1", "Build REST API", "Build a REST API", 0, "user1"),
    )
    await conn.commit()

    yield conn

    await conn.close()


# --- GitLab Credentials Tests ---


class TestGitLabCredentials:
    @pytest.mark.asyncio
    async def test_save_gitlab_credentials(self, db):
        """User can save GitLab server and token."""
        await db.execute(
            "UPDATE users SET gitlab_server = ?, gitlab_token_encrypted = ? WHERE id = ?",
            ("https://gitlab.example.com", "glpat-abc123", "user1"),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT gitlab_server, gitlab_token_encrypted FROM users WHERE id = ?",
            ("user1",),
        )
        row = await cursor.fetchone()
        assert row["gitlab_server"] == "https://gitlab.example.com"
        assert row["gitlab_token_encrypted"] == "glpat-abc123"

    @pytest.mark.asyncio
    async def test_gitlab_credentials_default_empty(self, db):
        """GitLab credentials default to empty strings."""
        cursor = await db.execute(
            "SELECT gitlab_server, gitlab_token_encrypted FROM users WHERE id = ?",
            ("user1",),
        )
        row = await cursor.fetchone()
        assert row["gitlab_server"] == ""
        assert row["gitlab_token_encrypted"] == ""


# --- Link Project Tests ---


class TestLinkProject:
    @pytest.mark.asyncio
    async def test_link_gitlab_project_updates_board_settings(self, db):
        """Linking a GitLab project stores settings in board.settings_json."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "project_path": "group/my-project",
                "project_url": "https://gitlab.example.com/group/my-project",
                "default_branch": "main",
                "auto_push": True,
            }
        }

        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        cursor = await db.execute("SELECT settings_json FROM boards WHERE id = ?", ("board1",))
        row = await cursor.fetchone()
        loaded = json.loads(row["settings_json"])
        assert loaded["gitlab"]["project_id"] == 42
        assert loaded["gitlab"]["project_path"] == "group/my-project"
        assert loaded["gitlab"]["auto_push"] is True


# --- GitLab Push Task Tests ---


class TestGitLabPushTask:
    @pytest.mark.asyncio
    async def test_create_gitlab_push_task(self, db):
        """Can create a gitlab_push task."""
        payload = json.dumps(
            {
                "project_id": 42,
                "project_path": "group/my-project",
                "default_branch": "main",
                "create_mr": True,
            }
        )

        task = await create_task(
            db,
            task_type="gitlab_push",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            payload_json=payload,
        )

        assert task["task_type"] == "gitlab_push"
        assert task["status"] == "pending"
        assert task["card_id"] == "card1"

        # Verify payload was stored
        loaded_payload = json.loads(task["payload_json"])
        assert loaded_payload["project_id"] == 42
        assert loaded_payload["create_mr"] is True

    @pytest.mark.asyncio
    async def test_create_gitlab_create_project_task(self, db):
        """Can create a gitlab_create_project task."""
        payload = json.dumps(
            {
                "name": "new-project",
                "visibility": "private",
            }
        )

        task = await create_task(
            db,
            task_type="gitlab_create_project",
            board_id="board1",
            created_by="user1",
            assigned_to="user1",
            payload_json=payload,
        )

        assert task["task_type"] == "gitlab_create_project"
        assert task["status"] == "pending"


# --- Auto-chain Tests ---


class TestAutoChainGitLabPush:
    @pytest.mark.asyncio
    async def test_coder_completion_on_gitlab_board_creates_push_task(self, db):
        """Coder completion on gitlab-linked board creates gitlab_push task."""
        # Set up board with GitLab settings
        settings = {
            "gitlab": {
                "project_id": 42,
                "project_path": "group/my-project",
                "default_branch": "main",
                "auto_push": True,
                "mr_prefix": "kira/",
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        # Create a coder agent task
        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="coder",
            prompt_text="Implement the API",
        )

        # Claim the task
        await db.execute(
            "UPDATE tasks SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task["id"],),
        )
        await db.commit()

        # Complete the task
        await complete_task(db, task["id"], output_text="Done implementing")

        # Check that a gitlab_push task was auto-created
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE task_type = 'gitlab_push' AND board_id = 'board1'"
        )
        push_tasks = await cursor.fetchall()
        assert len(push_tasks) == 1

        push_task = dict(push_tasks[0])
        assert push_task["card_id"] == "card1"
        assert push_task["created_by"] == "user1"
        assert push_task["status"] == "pending"

        push_payload = json.loads(push_task["payload_json"])
        assert push_payload["project_id"] == 42
        assert push_payload["project_path"] == "group/my-project"
        assert push_payload["create_mr"] is True

    @pytest.mark.asyncio
    async def test_no_auto_chain_when_auto_push_disabled(self, db):
        """No gitlab_push task is created when auto_push is False."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "auto_push": False,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="coder",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="Done")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_no_auto_chain_for_non_coder_agent(self, db):
        """No gitlab_push task is created for non-coder agents."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "auto_push": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="reviewer",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="LGTM")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_no_auto_chain_when_no_gitlab_settings(self, db):
        """No gitlab_push task when board has no gitlab settings."""
        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="coder",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="Done")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0


# --- Push on Complete Tests ---


class TestPushOnComplete:
    @pytest.mark.asyncio
    async def test_reviewer_completion_to_done_creates_push_task(self, db):
        """Reviewer completion moving card to terminal column creates gitlab_push."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "project_path": "group/my-project",
                "default_branch": "main",
                "auto_push": False,
                "push_on_complete": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="reviewer",
            target_column_id="col_done",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="LGTM")

        cursor = await db.execute(
            "SELECT * FROM tasks WHERE task_type = 'gitlab_push' AND board_id = 'board1'"
        )
        push_tasks = await cursor.fetchall()
        assert len(push_tasks) == 1

        push_task = dict(push_tasks[0])
        assert push_task["card_id"] == "card1"
        assert push_task["status"] == "pending"

        push_payload = json.loads(push_task["payload_json"])
        assert push_payload["project_id"] == 42
        assert push_payload["project_path"] == "group/my-project"
        assert push_payload["create_mr"] is True

    @pytest.mark.asyncio
    async def test_push_on_complete_skips_non_terminal_column(self, db):
        """No push_on_complete push when target column has automation."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "push_on_complete": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        # Target col_code which has auto_run=True, so it's NOT terminal
        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="architect",
            target_column_id="col_code",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="Design done")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_push_on_complete_disabled_no_push(self, db):
        """No push when push_on_complete is False even if card reaches terminal."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "push_on_complete": False,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="reviewer",
            target_column_id="col_done",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="LGTM")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_push_on_complete_deduplicates_with_auto_push(self, db):
        """When both auto_push and push_on_complete are on, coder to Done gets only one push."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "project_path": "group/my-project",
                "default_branch": "main",
                "auto_push": True,
                "push_on_complete": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        # Coder task targeting terminal column directly
        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="coder",
            target_column_id="col_done",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="Done coding")

        # auto_push creates one, push_on_complete should dedup and skip
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 1

    @pytest.mark.asyncio
    async def test_push_on_complete_rejected_reviewer_no_push(self, db):
        """No push_on_complete when reviewer rejects (is_rejected=True)."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "push_on_complete": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="reviewer",
            target_column_id="col_done",
            failure_column_id="col1",
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="REJECTED: issues found")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    @pytest.mark.asyncio
    async def test_push_on_complete_no_target_column_no_push(self, db):
        """No push_on_complete when task has no target_column_id."""
        settings = {
            "gitlab": {
                "project_id": 42,
                "push_on_complete": True,
            }
        }
        await db.execute(
            "UPDATE boards SET settings_json = ? WHERE id = ?",
            (json.dumps(settings), "board1"),
        )
        await db.commit()

        task = await create_task(
            db,
            task_type="agent_run",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            agent_type="reviewer",
            # No target_column_id
        )
        await db.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task["id"],))
        await db.commit()

        await complete_task(db, task["id"], output_text="LGTM")

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE task_type = 'gitlab_push'"
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0


# --- payload_json Rename Backward Compatibility ---


class TestPayloadJsonRename:
    @pytest.mark.asyncio
    async def test_jira_import_task_uses_payload_json(self, db):
        """Jira tasks use the renamed payload_json column."""
        payload = json.dumps({"jql": "project = TEST", "column_id": "col1"})

        task = await create_task(
            db,
            task_type="jira_import",
            board_id="board1",
            created_by="user1",
            assigned_to="user1",
            payload_json=payload,
        )

        assert task["task_type"] == "jira_import"
        loaded = json.loads(task["payload_json"])
        assert loaded["jql"] == "project = TEST"

    @pytest.mark.asyncio
    async def test_jira_push_task_uses_payload_json(self, db):
        """Jira push tasks also use payload_json correctly."""
        payload = json.dumps({"card_id": "card1"})

        task = await create_task(
            db,
            task_type="jira_push",
            board_id="board1",
            card_id="card1",
            created_by="user1",
            assigned_to="user1",
            payload_json=payload,
        )

        assert task["task_type"] == "jira_push"
        loaded = json.loads(task["payload_json"])
        assert loaded["card_id"] == "card1"
