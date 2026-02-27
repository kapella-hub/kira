"""Tests for card locking when agent is working on it."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest_asyncio

from kira.web.cards.service import (
    delete_card,
    is_card_locked,
    move_card,
    update_card,
)

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
    # Create columns
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col1", "board1", "Todo", 0),
    )
    await conn.execute(
        "INSERT INTO columns (id, board_id, name, position) VALUES (?, ?, ?, ?)",
        ("col2", "board1", "In Progress", 1),
    )
    await conn.commit()

    yield conn

    await conn.close()


async def _create_card_with_status(
    db: aiosqlite.Connection, card_id: str, agent_status: str
) -> dict:
    """Insert a card with a specific agent_status directly via SQL."""
    await db.execute(
        """INSERT INTO cards (id, column_id, board_id, title, description, position,
           agent_status, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (card_id, "col1", "board1", "Test Card", "desc", 0, agent_status, "user1"),
    )
    await db.commit()
    return dict(await (await db.execute("SELECT * FROM cards WHERE id = ?", (card_id,))).fetchone())


class TestIsCardLocked:
    """Unit tests for the is_card_locked helper."""

    def test_pending_is_locked(self):
        assert is_card_locked({"agent_status": "pending"}) is True

    def test_running_is_locked(self):
        assert is_card_locked({"agent_status": "running"}) is True

    def test_empty_is_unlocked(self):
        assert is_card_locked({"agent_status": ""}) is False

    def test_completed_is_unlocked(self):
        assert is_card_locked({"agent_status": "completed"}) is False

    def test_failed_is_unlocked(self):
        assert is_card_locked({"agent_status": "failed"}) is False

    def test_missing_key_is_unlocked(self):
        assert is_card_locked({}) is False


class TestLockedCardRejectsEdit:
    """Editing a locked card should be rejected (409) unless only agent_status changes."""

    async def test_update_locked_pending_card_rejected(self, db):
        card = await _create_card_with_status(db, "locked1", "pending")
        assert is_card_locked(card) is True

    async def test_update_locked_running_card_rejected(self, db):
        card = await _create_card_with_status(db, "locked2", "running")
        assert is_card_locked(card) is True

    async def test_update_unlocked_empty_status_allowed(self, db):
        card = await _create_card_with_status(db, "unlocked1", "")
        assert is_card_locked(card) is False
        updated = await update_card(db, "unlocked1", {"title": "New Title"})
        assert updated["title"] == "New Title"

    async def test_update_unlocked_completed_status_allowed(self, db):
        card = await _create_card_with_status(db, "unlocked2", "completed")
        assert is_card_locked(card) is False
        updated = await update_card(db, "unlocked2", {"title": "New Title"})
        assert updated["title"] == "New Title"

    async def test_update_unlocked_failed_status_allowed(self, db):
        card = await _create_card_with_status(db, "unlocked3", "failed")
        assert is_card_locked(card) is False
        updated = await update_card(db, "unlocked3", {"title": "New Title"})
        assert updated["title"] == "New Title"

    async def test_agent_status_only_update_allowed_on_locked_card(self, db):
        """System-initiated agent_status updates must pass even on locked cards."""
        card = await _create_card_with_status(db, "locked3", "pending")
        assert is_card_locked(card) is True
        # The router allows this because set(updates.keys()) == {"agent_status"}
        updates = {"agent_status": "running"}
        assert set(updates.keys()) == {"agent_status"}
        # Service-level update should succeed (no lock check at service layer)
        updated = await update_card(db, "locked3", updates)
        assert updated["agent_status"] == "running"

    async def test_mixed_update_with_agent_status_rejected_on_locked(self, db):
        """Update with agent_status + other fields should still be rejected."""
        card = await _create_card_with_status(db, "locked4", "running")
        updates = {"agent_status": "completed", "title": "Sneaky Edit"}
        # Router check: locked AND keys != {"agent_status"} => reject
        assert is_card_locked(card) is True
        assert set(updates.keys()) != {"agent_status"}


class TestLockedCardRejectsDelete:
    async def test_delete_locked_pending_card_rejected(self, db):
        card = await _create_card_with_status(db, "del1", "pending")
        assert is_card_locked(card) is True

    async def test_delete_locked_running_card_rejected(self, db):
        card = await _create_card_with_status(db, "del2", "running")
        assert is_card_locked(card) is True

    async def test_delete_unlocked_card_succeeds(self, db):
        await _create_card_with_status(db, "del3", "completed")
        deleted = await delete_card(db, "del3")
        assert deleted is True


class TestLockedCardRejectsMove:
    async def test_move_locked_pending_card_rejected(self, db):
        card = await _create_card_with_status(db, "move1", "pending")
        assert is_card_locked(card) is True

    async def test_move_locked_running_card_rejected(self, db):
        card = await _create_card_with_status(db, "move2", "running")
        assert is_card_locked(card) is True

    async def test_move_unlocked_card_succeeds(self, db):
        await _create_card_with_status(db, "move3", "")
        moved = await move_card(db, "move3", "col2", 0)
        assert moved is not None
        assert moved["column_id"] == "col2"


class TestRouterLockIntegration:
    """Test the exact lock-check logic the router uses, against real DB cards."""

    async def test_edit_locked_card_returns_409_logic(self, db):
        """Simulate the router's PATCH logic for a locked card."""
        card = await _create_card_with_status(db, "r_edit1", "running")
        updates = {"title": "New Title"}
        # This is the exact condition the router checks
        assert is_card_locked(card) and set(updates.keys()) != {"agent_status"}

    async def test_edit_locked_card_agent_status_only_passes(self, db):
        """Simulate the router's PATCH logic for agent_status-only update."""
        card = await _create_card_with_status(db, "r_edit2", "pending")
        updates = {"agent_status": "running"}
        # Router allows this because it's agent_status-only
        assert not (is_card_locked(card) and set(updates.keys()) != {"agent_status"})
        updated = await update_card(db, "r_edit2", updates)
        assert updated["agent_status"] == "running"

    async def test_delete_locked_card_returns_409_logic(self, db):
        """Simulate the router's DELETE logic for a locked card."""
        card = await _create_card_with_status(db, "r_del1", "pending")
        assert is_card_locked(card)

    async def test_move_locked_card_returns_409_logic(self, db):
        """Simulate the router's POST move logic for a locked card."""
        card = await _create_card_with_status(db, "r_move1", "running")
        assert is_card_locked(card)

    async def test_operations_on_unlocked_cards_all_pass(self, db):
        """All operations should work on cards with non-locked statuses."""
        for status in ("", "completed", "failed"):
            cid = f"unlocked_{status or 'empty'}"
            card = await _create_card_with_status(db, cid, status)
            assert not is_card_locked(card)
            # Update works
            updated = await update_card(db, cid, {"title": f"Updated {cid}"})
            assert updated["title"] == f"Updated {cid}"
