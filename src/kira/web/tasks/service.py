"""Task service - business logic."""

from __future__ import annotations

import secrets

import aiosqlite

from ..events import Event, EventType, event_manager


async def create_task(
    db: aiosqlite.Connection,
    task_type: str,
    board_id: str,
    created_by: str,
    card_id: str | None = None,
    assigned_to: str | None = None,
    agent_type: str = "",
    agent_skill: str = "",
    agent_model: str = "smart",
    prompt_text: str = "",
    payload_json: str = "{}",
    priority: int = 0,
    source_column_id: str = "",
    target_column_id: str = "",
    failure_column_id: str = "",
    loop_count: int = 0,
    max_loop_count: int = 3,
) -> dict:
    """Create a new task and publish event."""
    task_id = secrets.token_hex(8)

    await db.execute(
        """INSERT INTO tasks (id, task_type, board_id, card_id, created_by, assigned_to,
           agent_type, agent_skill, agent_model, prompt_text, payload_json,
           priority, source_column_id, target_column_id, failure_column_id,
           loop_count, max_loop_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            task_type,
            board_id,
            card_id,
            created_by,
            assigned_to,
            agent_type,
            agent_skill,
            agent_model,
            prompt_text,
            payload_json,
            priority,
            source_column_id,
            target_column_id,
            failure_column_id,
            loop_count,
            max_loop_count,
        ),
    )

    # Update card agent_status if card-linked
    if card_id:
        await db.execute("UPDATE cards SET agent_status = 'pending' WHERE id = ?", (card_id,))

    await db.commit()

    task = await get_task(db, task_id)
    await event_manager.publish_to_board(
        board_id, Event(event_type=EventType.TASK_CREATED, data=task)
    )
    return task


async def get_tasks(
    db: aiosqlite.Connection,
    board_id: str | None = None,
    card_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List tasks with optional filters."""
    conditions = []
    params: list[str] = []

    if board_id:
        conditions.append("board_id = ?")
        params.append(board_id)
    if card_id:
        conditions.append("card_id = ?")
        params.append(card_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await db.execute(f"SELECT * FROM tasks{where} ORDER BY created_at DESC", params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_task(db: aiosqlite.Connection, task_id: str) -> dict | None:
    """Get a task by ID."""
    cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def poll_tasks(
    db: aiosqlite.Connection,
    user_id: str,
    limit: int = 1,
) -> list[dict]:
    """Poll pending tasks for a user's worker.

    Returns tasks that are either:
      - Directly assigned to this user, OR
      - Unassigned but on a board where this user is a member
    """
    cursor = await db.execute(
        """SELECT t.* FROM tasks t
           WHERE t.status = 'pending'
             AND (t.assigned_to = ?
                  OR t.board_id IN (SELECT board_id FROM board_members WHERE user_id = ?))
           ORDER BY t.priority DESC, t.created_at ASC
           LIMIT ?""",
        (user_id, user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def claim_task(
    db: aiosqlite.Connection,
    task_id: str,
    worker_id: str,
) -> dict | None:
    """Atomically claim a pending task. Returns None if already claimed."""
    cursor = await db.execute(
        """UPDATE tasks SET status = 'claimed',
           claimed_by_worker = ?, claimed_at = CURRENT_TIMESTAMP
           WHERE id = ? AND status = 'pending'""",
        (worker_id, task_id),
    )
    if cursor.rowcount == 0:
        return None

    await db.commit()

    task = await get_task(db, task_id)
    if task:
        await event_manager.publish_to_board(
            task["board_id"],
            Event(event_type=EventType.TASK_CLAIMED, data=task),
        )
    return task


async def update_progress(
    db: aiosqlite.Connection,
    task_id: str,
    progress_text: str = "",
    *,
    step: int | None = None,
    total_steps: int | None = None,
    phase: str | None = None,
) -> dict | None:
    """Update task to running status with progress info."""
    task = await get_task(db, task_id)
    if not task:
        return None

    # Set started_at only on first progress call
    if task["status"] in ("claimed", "pending"):
        await db.execute(
            """UPDATE tasks SET status = 'running', started_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (task_id,),
        )
    else:
        await db.execute(
            "UPDATE tasks SET status = 'running' WHERE id = ?",
            (task_id,),
        )

    # Update card agent_status
    if task["card_id"]:
        await db.execute(
            "UPDATE cards SET agent_status = 'running' WHERE id = ?",
            (task["card_id"],),
        )

    await db.commit()

    task = await get_task(db, task_id)

    event_data: dict = {
        "task_id": task_id,
        "progress_text": progress_text,
        "task": task,
    }
    if step is not None:
        event_data["step"] = step
    if total_steps is not None:
        event_data["total_steps"] = total_steps
    if phase is not None:
        event_data["phase"] = phase

    await event_manager.publish_to_board(
        task["board_id"],
        Event(
            event_type=EventType.TASK_PROGRESS,
            data=event_data,
        ),
    )
    return task


async def complete_task(
    db: aiosqlite.Connection,
    task_id: str,
    output_text: str = "",
    result_data: dict | None = None,
) -> dict:
    """Complete a task with automation flow.

    1. Mark task completed
    2. Save output as card comment if present
    3. Check for reviewer rejection
    4. Move card to target/failure column
    5. Trigger automation on target column (but NOT on failure column)
    """
    task = await get_task(db, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    # 1. Mark completed
    await db.execute(
        """UPDATE tasks SET status = 'completed', completed_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (task_id,),
    )

    # 2. Save output as card comment
    comment_id = ""
    if output_text and task["card_id"]:
        comment_id = secrets.token_hex(8)
        await db.execute(
            """INSERT INTO card_comments (id, card_id, user_id, content, is_agent_output)
               VALUES (?, ?, ?, ?, 1)""",
            (comment_id, task["card_id"], task["created_by"], output_text),
        )
        await db.execute(
            "UPDATE tasks SET output_comment_id = ? WHERE id = ?",
            (comment_id, task_id),
        )

    # 3. Check reviewer rejection
    is_rejected = (
        task["agent_type"] == "reviewer" and output_text and "REJECTED" in output_text.upper()
    )

    # 4. Determine which column to move to
    if is_rejected:
        # Reviewer rejected: treat as failure path
        move_to_column = task["failure_column_id"]
        trigger_automation = False
        await db.execute(
            "UPDATE tasks SET status = 'failed', error_summary = 'Reviewer rejected' WHERE id = ?",
            (task_id,),
        )
        if task["card_id"]:
            await db.execute(
                "UPDATE cards SET agent_status = 'failed' WHERE id = ?",
                (task["card_id"],),
            )
    else:
        move_to_column = task["target_column_id"]
        trigger_automation = True
        if task["card_id"]:
            await db.execute(
                "UPDATE cards SET agent_status = 'completed' WHERE id = ?",
                (task["card_id"],),
            )

    await db.commit()

    next_action = None

    # 5. Move card if target column is set
    if move_to_column and task["card_id"]:
        from ..cards.service import move_card

        moved_card = await move_card(
            db,
            task["card_id"],
            move_to_column,
            0,
            user_id=task["created_by"],
            skip_automation=not trigger_automation,
        )
        if moved_card:
            next_action = {
                "type": "card_moved",
                "card_id": task["card_id"],
                "to_column_id": move_to_column,
                "automation_triggered": trigger_automation,
            }

    # Load board settings once for steps 6 & 7
    gitlab_settings = {}
    if not is_rejected and task["board_id"]:
        board_cursor = await db.execute(
            "SELECT settings_json FROM boards WHERE id = ?", (task["board_id"],)
        )
        board_row = await board_cursor.fetchone()
        if board_row:
            import json

            settings = json.loads(board_row["settings_json"] or "{}")
            gitlab_settings = settings.get("gitlab", {})

    # 6. Auto-chain gitlab_push after coder task if auto_push enabled
    if (
        not is_rejected
        and task["agent_type"] == "coder"
        and task["card_id"]
        and gitlab_settings.get("auto_push")
        and gitlab_settings.get("project_id")
    ):
        import json

        await create_task(
            db,
            task_type="gitlab_push",
            board_id=task["board_id"],
            card_id=task["card_id"],
            created_by=task["created_by"],
            payload_json=json.dumps(
                {
                    "project_id": gitlab_settings["project_id"],
                    "project_path": gitlab_settings.get("project_path", ""),
                    "default_branch": gitlab_settings.get("default_branch", "main"),
                    "mr_prefix": gitlab_settings.get("mr_prefix", "kira/"),
                    "create_mr": True,
                }
            ),
        )

    # 7. Auto-chain gitlab_push when card reaches terminal column (push_on_complete)
    if (
        not is_rejected
        and move_to_column
        and task["card_id"]
        and gitlab_settings.get("push_on_complete")
        and gitlab_settings.get("project_id")
    ):
        # Check if target column is terminal (no automation)
        col_cursor = await db.execute(
            "SELECT auto_run, agent_type FROM columns WHERE id = ?",
            (move_to_column,),
        )
        col_row = await col_cursor.fetchone()
        if col_row and not col_row["auto_run"] and not col_row["agent_type"]:
            # Deduplicate: skip if a gitlab_push is already pending for this card
            import json

            dup_cursor = await db.execute(
                """SELECT id FROM tasks
                   WHERE card_id = ? AND task_type = 'gitlab_push'
                     AND status IN ('pending', 'claimed', 'running')
                   LIMIT 1""",
                (task["card_id"],),
            )
            if not await dup_cursor.fetchone():
                await create_task(
                    db,
                    task_type="gitlab_push",
                    board_id=task["board_id"],
                    card_id=task["card_id"],
                    created_by=task["created_by"],
                    payload_json=json.dumps(
                        {
                            "project_id": gitlab_settings["project_id"],
                            "project_path": gitlab_settings.get("project_path", ""),
                            "default_branch": gitlab_settings.get("default_branch", "main"),
                            "mr_prefix": gitlab_settings.get("mr_prefix", "kira/"),
                            "create_mr": True,
                        }
                    ),
                )

    # 8. Auto-chain card_gen after board_plan if requested
    if not is_rejected and task["task_type"] == "board_plan":
        import json

        payload = json.loads(task["payload_json"] or "{}")
        if payload.get("auto_generate_cards"):
            # Find target column (prefer "Plan" or "Backlog", fallback to first)
            col_cursor = await db.execute(
                "SELECT id, name FROM columns WHERE board_id = ? ORDER BY position ASC",
                (task["board_id"],),
            )
            columns = await col_cursor.fetchall()
            target_col = columns[0]["id"] if columns else ""
            for col in columns:
                if col["name"].lower() in ("plan", "backlog"):
                    target_col = col["id"]
                    break

            if target_col:
                await create_task(
                    db,
                    task_type="card_gen",
                    board_id=task["board_id"],
                    created_by=task["created_by"],
                    agent_type="architect",
                    agent_model="smart",
                    prompt_text=task["prompt_text"],
                    payload_json=json.dumps({"target_column_id": target_col}),
                )

    # 9. Publish event
    task = await get_task(db, task_id)
    status_event = EventType.TASK_FAILED if is_rejected else EventType.TASK_COMPLETED
    await event_manager.publish_to_board(
        task["board_id"],
        Event(event_type=status_event, data={"task": task, "next_action": next_action}),
    )

    task["next_action"] = next_action
    return task


async def fail_task(
    db: aiosqlite.Connection,
    task_id: str,
    error_summary: str = "",
    output_text: str = "",
) -> dict:
    """Fail a task with automation flow.

    1. Mark task failed
    2. Save output as card comment if present
    3. Move card to failure column (without triggering auto_run)
    """
    task = await get_task(db, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    # 1. Mark failed
    await db.execute(
        """UPDATE tasks SET status = 'failed', error_summary = ?,
           completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
        (error_summary, task_id),
    )

    # 2. Save output as card comment
    if output_text and task["card_id"]:
        comment_id = secrets.token_hex(8)
        await db.execute(
            """INSERT INTO card_comments (id, card_id, user_id, content, is_agent_output)
               VALUES (?, ?, ?, ?, 1)""",
            (comment_id, task["card_id"], task["created_by"], output_text),
        )
        await db.execute(
            "UPDATE tasks SET output_comment_id = ? WHERE id = ?",
            (comment_id, task_id),
        )

    # 3. Update card agent_status
    if task["card_id"]:
        await db.execute(
            "UPDATE cards SET agent_status = 'failed' WHERE id = ?",
            (task["card_id"],),
        )

    await db.commit()

    next_action = None

    # 4. Move card to failure column (skip automation to prevent infinite loops)
    if task["failure_column_id"] and task["card_id"]:
        from ..cards.service import move_card

        moved_card = await move_card(
            db,
            task["card_id"],
            task["failure_column_id"],
            0,
            user_id=task["created_by"],
            skip_automation=True,
        )
        if moved_card:
            next_action = {
                "type": "card_moved",
                "card_id": task["card_id"],
                "to_column_id": task["failure_column_id"],
                "automation_triggered": False,
            }

    # 5. Publish event
    task = await get_task(db, task_id)
    await event_manager.publish_to_board(
        task["board_id"],
        Event(event_type=EventType.TASK_FAILED, data={"task": task, "next_action": next_action}),
    )

    task["next_action"] = next_action
    return task


async def cancel_task(db: aiosqlite.Connection, task_id: str) -> dict | None:
    """Cancel a pending or running task."""
    task = await get_task(db, task_id)
    if not task:
        return None

    if task["status"] not in ("pending", "claimed", "running"):
        raise ValueError(f"Cannot cancel task in status '{task['status']}'")

    await db.execute(
        """UPDATE tasks SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (task_id,),
    )

    if task["card_id"]:
        await db.execute(
            "UPDATE cards SET agent_status = '' WHERE id = ?",
            (task["card_id"],),
        )

    await db.commit()

    task = await get_task(db, task_id)
    await event_manager.publish_to_board(
        task["board_id"],
        Event(event_type=EventType.TASK_CANCELLED, data=task),
    )
    return task
