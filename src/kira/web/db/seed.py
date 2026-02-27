"""Seed database with demo data."""

from __future__ import annotations

import secrets

import aiosqlite


def _id() -> str:
    return secrets.token_hex(8)


async def seed_db(db: aiosqlite.Connection) -> None:
    """Seed database with demo users, board, and agent-workflow columns."""

    # Check if already seeded
    cursor = await db.execute("SELECT COUNT(*) FROM users")
    row = await cursor.fetchone()
    if row[0] > 0:
        return

    # --- Users ---
    alice_id = _id()
    bob_id = _id()
    charlie_id = _id()

    users = [
        (alice_id, "alice", "Alice Johnson", "", "{}"),
        (bob_id, "bob", "Bob Smith", "", "{}"),
        (charlie_id, "charlie", "Charlie Davis", "", "{}"),
    ]
    await db.executemany(
        """INSERT INTO users (id, username, display_name, avatar_url, preferences_json)
           VALUES (?, ?, ?, ?, ?)""",
        users,
    )

    # --- Board ---
    board_id = _id()
    await db.execute(
        """INSERT INTO boards (id, name, description, owner_id) VALUES (?, ?, ?, ?)""",
        (board_id, "Sprint Board", "Main development sprint board", alice_id),
    )

    # Add all users as board members
    await db.executemany(
        "INSERT INTO board_members (board_id, user_id, role) VALUES (?, ?, ?)",
        [
            (board_id, alice_id, "owner"),
            (board_id, bob_id, "admin"),
            (board_id, charlie_id, "member"),
        ],
    )

    # --- Columns (the board IS the workflow) ---
    col_backlog = _id()
    col_architect = _id()
    col_code = _id()
    col_review = _id()
    col_done = _id()

    # Backlog: no automation
    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, wip_limit, color,
           agent_type, auto_run, on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (col_backlog, board_id, "Backlog", 0, 0, "#64748b", "", 0, "", "", 3),
    )
    # Architect: auto-run architect agent, on success -> Code
    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, wip_limit, color,
           agent_type, auto_run, on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (col_architect, board_id, "Architect", 1, 3, "#6366f1", "architect", 1, col_code, "", 3),
    )
    # Code: auto-run coder agent, on success -> Review
    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, wip_limit, color,
           agent_type, auto_run, on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (col_code, board_id, "Code", 2, 3, "#f59e0b", "coder", 1, col_review, "", 3),
    )
    # Review: auto-run reviewer agent, on success -> Done, on failure -> Code (loop!)
    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, wip_limit, color,
           agent_type, auto_run, on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (col_review, board_id, "Review", 3, 3, "#8b5cf6", "reviewer", 1, col_done, col_code, 3),
    )
    # Done: no automation
    await db.execute(
        """INSERT INTO columns (id, board_id, name, position, wip_limit, color,
           agent_type, auto_run, on_success_column_id, on_failure_column_id, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (col_done, board_id, "Done", 4, 0, "#22c55e", "", 0, "", "", 3),
    )

    # --- Cards ---
    cards = [
        (
            _id(),
            col_backlog,
            board_id,
            "Set up CI/CD pipeline",
            "Configure GitHub Actions for automated testing and deployment",
            0,
            None,
            "medium",
            '["devops"]',
            None,
            alice_id,
        ),
        (
            _id(),
            col_backlog,
            board_id,
            "Add dark mode support",
            "Implement theme switching with system preference detection",
            1,
            None,
            "low",
            '["frontend", "ux"]',
            None,
            bob_id,
        ),
        (
            _id(),
            col_backlog,
            board_id,
            "Design REST API endpoints",
            "Define OpenAPI spec for the user management service",
            2,
            alice_id,
            "high",
            '["backend", "api"]',
            None,
            alice_id,
        ),
        (
            _id(),
            col_done,
            board_id,
            "Project setup and scaffolding",
            "Initialize project structure, linting, and dev tooling",
            0,
            alice_id,
            "medium",
            '["devops"]',
            None,
            alice_id,
        ),
    ]

    await db.executemany(
        """INSERT INTO cards (id, column_id, board_id, title, description, position,
           assignee_id, priority, labels, due_date, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        cards,
    )

    await db.commit()
