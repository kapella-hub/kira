# Architecture v2: Board-Driven Workflow with Worker Protocol

## 1. Goals

- **The Board IS the Workflow**: Dragging a card into a column with `auto_run=true` triggers an agent task. No separate workflow builder.
- **Client/Server Split**: Server (FastAPI) manages shared state. Workers (local Python processes) execute kiro-cli and Jira operations with local credentials.
- **Visible Automation Loops**: Reviewer rejects -> card moves back to "Code" -> coder re-runs. The loop is visible on the board as card movement.
- **Remove Dead Code**: Eliminate unused CLI modules (memory, skills, thinking, workflows, correction, context, git, logs, tools, rules, personality).

## 2. Non-Goals

- **Multi-tenancy / RBAC overhaul**: Keep the existing mock auth for now. Real auth is a separate effort.
- **Workflow builder UI**: Eliminated by design. Columns ARE the workflow.
- **Database migration to PostgreSQL**: Stay on SQLite for now. The schema changes are additive.
- **Horizontal worker scaling**: One worker per user is sufficient. No worker pool orchestration.
- **Jira webhook push**: Workers poll; Jira does not push events to us.

## 3. Assumptions

- Each user runs exactly one worker process on their local machine.
- kiro-cli is installed locally on every developer's machine.
- The server is reachable from each developer's machine (Rancher deployment or localhost for dev).
- Jira credentials never leave the worker machine (stored in `~/.kira/jira.yaml` or env vars).
- SQLite is adequate for the current team size (<20 concurrent users). If this assumption is wrong, PostgreSQL migration would be needed.
- A single worker handles tasks sequentially (or with limited concurrency). CPU-bound kiro-cli processes are the bottleneck, not the worker framework.

## 4. Proposed Architecture

### 4.1 High-Level Overview

```
+-------------------+     +---------------------------+     +-------------------+
|   React Frontend  |     |    FastAPI Server          |     |   Local Worker    |
|   (static build)  |<--->|    (Rancher / localhost)   |<--->|   (per user)      |
|                   | API |                            | API |                   |
|   - Board UI      |     |   - Board/Card/Column CRUD |     |   - Polls /tasks  |
|   - Column config |     |   - Task queue (DB-backed) |     |   - Runs kiro-cli |
|   - Card drag     |     |   - Worker registry        |     |   - Runs Jira ops |
|   - SSE stream    |     |   - SSE events             |     |   - Heartbeats    |
|   - Worker status |     |   - Automation trigger     |     |   - Reports result|
+-------------------+     +---------------------------+     +-------------------+
```

### 4.2 Component Responsibilities

**Server (FastAPI)** -- `/Users/P2799106/Projects/kira/src/kira/web/`
- Board, Column, Card, Comment CRUD
- Worker registration and heartbeat tracking
- Task queue: create tasks, assign to workers, track status
- Automation trigger: when a card moves to an `auto_run` column, create a task
- SSE event broadcasting for real-time UI updates
- Search (ChromaDB + SQLite fallback)
- Auth (mock JWT -- unchanged)

**Worker (Python process)** -- new `src/kira/worker/`
- Registers with server on startup (POST /api/workers/register)
- Polls server for tasks assigned to its user (GET /api/workers/tasks/poll)
- Sends heartbeats (POST /api/workers/heartbeat)
- Executes kiro-cli via `KiraClient` with local credentials
- Executes Jira operations via `JiraClient` with local credentials
- Reports task progress/completion/failure back to server
- Handles graceful shutdown (deregisters)

**Frontend (React)** -- `/Users/P2799106/Projects/kira/frontend/`
- Board view with drag-and-drop
- Column configuration panel (agent_type, auto_run, success/failure routing)
- Card detail with agent run history
- Worker status indicator (online/offline per user)
- Task status indicators on cards
- Jira import/push UI (triggers tasks, not direct Jira calls)

### 4.3 Key Design Decisions

| Decision | Rationale |
|---|---|
| DB-backed task queue instead of RabbitMQ/Redis | Simplicity. SQLite is already in use. Task volume is low (tens/hour, not thousands). No new infrastructure needed. |
| Worker polls instead of WebSocket push | Workers may be behind NAT/firewalls. Polling is simpler, debuggable, and works through any proxy. 5-second poll interval is fine for agent tasks that take minutes. |
| `workflows` table removed | The board IS the workflow. Column `auto_run` + `on_success_column_id` + `on_failure_column_id` encode the entire flow. |
| `agent_runs` table replaced by `tasks` table | `agent_runs` was server-side with no worker concept. `tasks` is the new unified queue for both agent and Jira operations. |
| No task result storage in DB | Task output goes into `card_comments` as an agent comment. The `tasks` table stores only status, error summary, and timing. Large outputs belong in comments, not in a status table. |
| Jira operations become tasks | Server never calls Jira directly. "Import from Jira" creates a `jira_import` task. Worker executes it and creates cards via the server API. |

---

## 5. Database Schema

### 5.1 Tables to KEEP (unchanged)

- `users` -- unchanged
- `boards` -- unchanged
- `board_members` -- unchanged
- `columns` -- unchanged (already has `agent_type`, `auto_run`, `on_success_column_id`, etc.)
- `cards` -- unchanged
- `card_comments` -- unchanged
- `card_activity` -- unchanged

### 5.2 Tables to REMOVE

- `agent_runs` -- replaced by `tasks`
- `workflows` -- columns ARE the workflow; this table is unnecessary

### 5.3 Tables to ADD

```sql
-- Workers: registered worker instances
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hostname TEXT NOT NULL DEFAULT '',
    worker_version TEXT NOT NULL DEFAULT '',
    -- Capabilities the worker advertises
    capabilities_json TEXT NOT NULL DEFAULT '["agent", "jira"]',
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'online' CHECK (status IN ('online', 'offline', 'stale')),
    last_heartbeat TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Configuration the server can push via heartbeat response
    max_concurrent_tasks INTEGER DEFAULT 1,
    UNIQUE(user_id)  -- One worker per user
);

-- Tasks: unified queue for agent runs, jira operations, and any future task types
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    -- What
    task_type TEXT NOT NULL CHECK (task_type IN (
        'agent_run',           -- Run kiro-cli agent on a card
        'jira_import',         -- Import issues from Jira
        'jira_push',           -- Push card to Jira
        'jira_sync'            -- Sync board with Jira
    )),
    -- Context
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    -- Assignment
    assigned_to TEXT REFERENCES users(id),           -- Which user's worker should execute this
    claimed_by_worker TEXT REFERENCES workers(id),   -- Which worker instance claimed it
    -- Agent-specific fields
    agent_type TEXT DEFAULT '',                       -- e.g. 'architect', 'coder', 'reviewer'
    agent_skill TEXT DEFAULT '',
    agent_model TEXT DEFAULT 'smart',
    prompt_text TEXT DEFAULT '',                      -- The full prompt sent to kiro-cli
    -- Jira-specific fields
    jira_payload_json TEXT DEFAULT '{}',              -- JQL, card_id, board_id, etc.
    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',    -- Created, waiting for worker
        'claimed',    -- Worker has claimed it, about to start
        'running',    -- Actively executing
        'completed',  -- Finished successfully
        'failed',     -- Finished with error
        'cancelled'   -- Manually cancelled
    )),
    priority INTEGER NOT NULL DEFAULT 0,              -- Higher = more urgent
    -- Automation context
    source_column_id TEXT REFERENCES columns(id),     -- Column the card was in when task was created
    target_column_id TEXT REFERENCES columns(id),     -- Column to move card to on success
    failure_column_id TEXT REFERENCES columns(id),    -- Column to move card to on failure
    loop_count INTEGER DEFAULT 0,                     -- How many times this card has looped through this column
    max_loop_count INTEGER DEFAULT 3,                 -- Inherited from column config
    -- Results
    error_summary TEXT DEFAULT '',                    -- Short error message (full output goes to card_comments)
    output_comment_id TEXT REFERENCES card_comments(id),  -- Link to the comment containing full output
    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Indexes for task polling and status queries
CREATE INDEX IF NOT EXISTS idx_tasks_poll
    ON tasks(assigned_to, status)
    WHERE status IN ('pending', 'claimed');

CREATE INDEX IF NOT EXISTS idx_tasks_board
    ON tasks(board_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_card
    ON tasks(card_id)
    WHERE card_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status, created_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_workers_user
    ON workers(user_id);

CREATE INDEX IF NOT EXISTS idx_workers_status
    ON workers(status)
    WHERE status = 'online';
```

### 5.4 Migration Strategy

Migration runs in `_run_migrations()` inside `/Users/P2799106/Projects/kira/src/kira/web/db/database.py`:

1. CREATE `workers` table (IF NOT EXISTS -- safe to re-run).
2. CREATE `tasks` table (IF NOT EXISTS).
3. CREATE indexes.
4. Migrate any existing `agent_runs` rows to `tasks` (one-time, best-effort).
5. DROP `workflows` table (or leave it as dead weight if we want zero risk).

---

## 6. API Contracts

### 6.1 Worker Protocol

#### POST /api/workers/register
Worker registers on startup. Returns worker ID and server-side config.

**Request:**
```json
{
  "hostname": "alice-macbook",
  "worker_version": "0.3.0",
  "capabilities": ["agent", "jira"]
}
```

**Response (201):**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8",
  "max_concurrent_tasks": 1,
  "poll_interval_seconds": 5,
  "heartbeat_interval_seconds": 30
}
```

**Auth:** Bearer JWT (same as all endpoints). `user_id` extracted from token.

**Behavior:**
- If a worker already exists for this user, update it (re-register).
- Set `status = 'online'`, `last_heartbeat = NOW`.

---

#### POST /api/workers/heartbeat
Worker sends heartbeat every 30 seconds.

**Request:**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8",
  "running_task_ids": ["task1", "task2"],
  "system_load": 0.45
}
```

**Response (200):**
```json
{
  "status": "ok",
  "directives": {
    "max_concurrent_tasks": 1,
    "cancel_task_ids": []
  }
}
```

**Behavior:**
- Update `last_heartbeat` on the worker row.
- If `running_task_ids` contains tasks the server thinks are cancelled, include them in `cancel_task_ids`.
- Server marks workers as `stale` if no heartbeat for 90 seconds, `offline` after 300 seconds.

---

#### GET /api/workers/tasks/poll
Worker polls for pending tasks assigned to its user.

**Query params:**
- `worker_id` (required)
- `limit` (optional, default 1)

**Response (200):**
```json
{
  "tasks": [
    {
      "id": "task_abc123",
      "task_type": "agent_run",
      "board_id": "board_xyz",
      "card_id": "card_456",
      "agent_type": "architect",
      "agent_skill": "architect",
      "agent_model": "smart",
      "prompt_text": "Design the authentication system...",
      "jira_payload_json": "{}",
      "priority": 0,
      "loop_count": 0,
      "max_loop_count": 3,
      "created_at": "2026-02-25T10:00:00Z"
    }
  ]
}
```

**Behavior:**
- Returns tasks WHERE `assigned_to = current_user` AND `status = 'pending'` ORDER BY `priority DESC, created_at ASC`.
- Does NOT claim the task. Worker must explicitly claim.

---

#### POST /api/workers/tasks/{task_id}/claim
Worker claims a task before starting execution.

**Request:**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8"
}
```

**Response (200):**
```json
{
  "status": "claimed",
  "task": { ... full task object ... }
}
```

**Response (409 Conflict):**
```json
{
  "detail": "Task already claimed"
}
```

**Behavior:**
- Atomic: UPDATE tasks SET status='claimed', claimed_by_worker=?, claimed_at=NOW WHERE id=? AND status='pending'.
- If 0 rows affected, return 409.
- Publishes `task_claimed` SSE event.

---

#### POST /api/workers/tasks/{task_id}/progress
Worker reports progress during execution (optional, for streaming output).

**Request:**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8",
  "status": "running",
  "progress_text": "Phase 2/4: Analyzing code structure..."
}
```

**Response (200):**
```json
{ "status": "ok" }
```

**Behavior:**
- Updates `tasks.status = 'running'`, `started_at = NOW` (first progress call only).
- Updates `cards.agent_status = 'running'`.
- Publishes `agent_progress` SSE event with `progress_text`.

---

#### POST /api/workers/tasks/{task_id}/complete
Worker reports successful completion.

**Request:**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8",
  "output_text": "## Architecture Design\n\nThe authentication system should...",
  "result_data": {}
}
```

**Response (200):**
```json
{
  "status": "completed",
  "next_action": {
    "type": "card_moved",
    "card_id": "card_456",
    "to_column_id": "col_review",
    "automation_triggered": true
  }
}
```

**Behavior:**
1. Update `tasks.status = 'completed'`, `completed_at = NOW`.
2. Create a `card_comment` with `is_agent_output = 1` containing `output_text`. Store comment ID in `tasks.output_comment_id`.
3. Update `cards.agent_status = 'completed'`.
4. **Automation**: Look up `target_column_id` (from the task, which was inherited from `columns.on_success_column_id`).
   - If set: Move the card to that column.
   - If the destination column has `auto_run = 1`: Create a NEW task for that column's agent. Increment `loop_count`. Check `max_loop_count`.
5. Publish SSE events: `agent_completed`, `card_updated`, and potentially `card_moved` + `agent_started`.
6. Return `next_action` so worker knows what happened (informational only -- server already did it).

---

#### POST /api/workers/tasks/{task_id}/fail
Worker reports failure.

**Request:**
```json
{
  "worker_id": "a1b2c3d4e5f6g7h8",
  "error_summary": "kiro-cli exited with code 1: timeout after 600s",
  "output_text": "Partial output before failure..."
}
```

**Response (200):**
```json
{
  "status": "failed",
  "next_action": {
    "type": "card_moved",
    "card_id": "card_456",
    "to_column_id": "col_backlog",
    "automation_triggered": false
  }
}
```

**Behavior:**
1. Update `tasks.status = 'failed'`, `tasks.error_summary`, `completed_at = NOW`.
2. If `output_text` is non-empty, create a `card_comment` with `is_agent_output = 1`.
3. Update `cards.agent_status = 'failed'`.
4. **Automation**: Look up `failure_column_id`.
   - If set: Move the card to that column. Do NOT trigger auto_run on the failure column (prevent infinite failure loops).
5. Publish SSE events.

---

#### POST /api/workers/tasks/{task_id}/cancel (called by server, not worker)
Cancel a running task. Already exists conceptually from `cancel_agent_run`.

**Behavior:**
- Sets `tasks.status = 'cancelled'`.
- Worker learns about cancellation via heartbeat response `cancel_task_ids`.
- Worker is responsible for killing the kiro-cli subprocess.

---

### 6.2 Task Management (called by frontend)

#### GET /api/tasks?board_id=X&status=running
List tasks for a board, filterable by status.

**Response:**
```json
[
  {
    "id": "task_abc",
    "task_type": "agent_run",
    "board_id": "board_xyz",
    "card_id": "card_456",
    "agent_type": "architect",
    "status": "running",
    "created_by": "user_alice",
    "assigned_to": "user_alice",
    "loop_count": 0,
    "created_at": "...",
    "started_at": "..."
  }
]
```

#### POST /api/tasks/{task_id}/cancel
Cancel a pending or running task (from frontend).

**Response:**
```json
{ "status": "cancelled" }
```

---

### 6.3 Automation Trigger (internal, not a direct API call)

The automation trigger fires inside the **card move** service logic.

**Current**: `card_service.move_card()` moves the card and publishes a `CARD_MOVED` event.

**New**: After the move, `move_card()` calls `automation.maybe_trigger(db, card, target_column)`:

```python
async def maybe_trigger(db, card: dict, column: dict, user_id: str) -> dict | None:
    """Check if the target column should auto-trigger an agent task.

    Returns the created task dict, or None if no automation.
    """
    if not column.get("auto_run") or not column.get("agent_type"):
        return None

    # Check loop count
    loop_count = await _get_loop_count(db, card["id"], column["id"])
    if loop_count >= column.get("max_loop_count", 3):
        return None  # Loop limit reached

    # Build prompt from template
    prompt = _render_prompt(column["prompt_template"], card)

    # Determine who should run this task
    assigned_to = card.get("assignee_id") or user_id

    # Create task
    task = await task_service.create_task(
        db,
        task_type="agent_run",
        board_id=card["board_id"],
        card_id=card["id"],
        created_by=user_id,
        assigned_to=assigned_to,
        agent_type=column["agent_type"],
        agent_skill=column.get("agent_skill", ""),
        agent_model=column.get("agent_model", "smart"),
        prompt_text=prompt,
        source_column_id=column["id"],
        target_column_id=column.get("on_success_column_id", ""),
        failure_column_id=column.get("on_failure_column_id", ""),
        loop_count=loop_count,
        max_loop_count=column.get("max_loop_count", 3),
    )

    # Update card agent_status
    await db.execute(
        "UPDATE cards SET agent_status = 'pending' WHERE id = ?",
        (card["id"],),
    )
    await db.commit()

    return task
```

### 6.4 Jira Operations (Task-Based)

All Jira operations become tasks. The frontend triggers them, and a worker executes them.

#### POST /api/jira/import (modified -- now creates a task)

**Request (unchanged):**
```json
{
  "jql": "project = MYPROJ AND sprint in openSprints()",
  "board_id": "board_xyz",
  "column_id": "col_backlog"
}
```

**Response (201 -- returns task, not cards):**
```json
{
  "task_id": "task_jira_import_1",
  "status": "pending",
  "message": "Jira import task queued. Your worker will execute it."
}
```

**Worker execution flow:**
1. Worker polls and gets a `jira_import` task with `jira_payload_json = {"jql": "...", "board_id": "...", "column_id": "..."}`.
2. Worker uses local Jira credentials to call Jira API.
3. Worker creates cards by calling server API: `POST /api/cards` for each imported issue.
4. Worker reports completion: `POST /api/workers/tasks/{id}/complete` with `result_data = {"imported": 5, "skipped": 2}`.

#### POST /api/jira/push/{card_id} (modified -- creates a task)

**Response (201):**
```json
{
  "task_id": "task_jira_push_1",
  "status": "pending"
}
```

#### POST /api/jira/sync/{board_id} (modified -- creates a task)

**Response (201):**
```json
{
  "task_id": "task_jira_sync_1",
  "status": "pending"
}
```

---

## 7. Worker Protocol -- Sequence Diagrams

### 7.1 Worker Registration + Authentication

```
Worker                          Server
  |                                |
  |-- POST /api/auth/login ------->|  (username -> JWT)
  |<-- { token, user } ------------|
  |                                |
  |-- POST /api/workers/register ->|  (hostname, version, capabilities)
  |<-- { worker_id, config } ------|
  |                                |
  |  [start heartbeat loop]        |
  |  [start task poll loop]        |
```

### 7.2 Task Lifecycle: Card Move -> Agent Execution -> Auto-Move

```
User drags card           Server                        Worker
to "Architect" column
  |                          |                             |
  |-- POST /cards/{id}/move->|                             |
  |                          |-- move_card()               |
  |                          |-- maybe_trigger()           |
  |                          |   column.auto_run? YES      |
  |                          |   column.agent_type=architect|
  |                          |   -> INSERT task (pending)  |
  |                          |   -> UPDATE card.agent_status='pending'
  |                          |-- SSE: card_moved           |
  |                          |-- SSE: agent_started        |
  |<-- card (moved) ---------|                             |
  |                          |                             |
  |                          |  [5 sec poll]               |
  |                          |<-- GET /workers/tasks/poll--|
  |                          |-- { tasks: [task] } ------->|
  |                          |                             |
  |                          |<-- POST /tasks/{id}/claim --|
  |                          |-- { claimed } ------------->|
  |                          |-- SSE: task_claimed         |
  |                          |                             |
  |                          |                             |-- kiro-cli subprocess
  |                          |                             |   (streaming output)
  |                          |<-- POST /tasks/{id}/progress|
  |                          |-- SSE: agent_progress       |
  |                          |                             |
  |                          |                             |-- kiro-cli exits 0
  |                          |<-- POST /tasks/{id}/complete|
  |                          |   { output_text: "..." }    |
  |                          |                             |
  |                          |-- INSERT card_comment       |
  |                          |-- UPDATE card.agent_status='completed'
  |                          |-- Auto-move: card -> on_success_column
  |                          |-- Maybe: create next task   |
  |                          |-- SSE: agent_completed      |
  |                          |-- SSE: card_moved           |
  |                          |-- SSE: agent_started (next) |
  |                          |                             |
  |<-- SSE events ----------|                             |
```

### 7.3 Review Rejection Loop

```
Board columns: [Backlog] -> [Architect] -> [Code] -> [Review] -> [Done]
                              auto_run       auto_run   auto_run
                              agent=architect agent=coder agent=reviewer
                              on_success=Code on_success=Review on_success=Done
                                              on_failure=Code   on_failure=Code

Card starts in "Architect":
  1. Architect agent runs -> success -> card moves to "Code"
  2. Coder agent runs -> success -> card moves to "Review"
  3. Reviewer agent runs -> FAILS (rejects) -> card moves to "Code" (loop_count=1)
  4. Coder agent runs again -> success -> card moves to "Review" (loop_count=1)
  5. Reviewer agent runs again -> success -> card moves to "Done"

If loop_count >= max_loop_count (default 3):
  - Card stays in the current column with agent_status='failed'
  - No further automation
  - User sees the failure and intervenes manually
```

### 7.4 Jira Import Flow

```
User clicks "Import"      Server                        Worker
  |                          |                             |
  |-- POST /api/jira/import->|                             |
  |   { jql, board, column } |                             |
  |                          |-- INSERT task (jira_import)  |
  |<-- { task_id, pending } -|                             |
  |                          |                             |
  |                          |<-- GET /workers/tasks/poll--|
  |                          |-- { tasks: [jira_import] }->|
  |                          |                             |
  |                          |<-- POST /tasks/{id}/claim --|
  |                          |                             |
  |                          |                             |-- JiraClient.search_issues()
  |                          |                             |   (using LOCAL creds)
  |                          |                             |
  |                          |                             |-- For each issue:
  |                          |<-- POST /api/cards ---------|   (create card via API)
  |                          |-- SSE: card_created         |
  |                          |                             |
  |                          |<-- POST /tasks/{id}/complete|
  |                          |   { result_data: {imported:5} }
  |                          |-- SSE: task_completed       |
```

---

## 8. Prompt Template Rendering

Column `prompt_template` supports these variables:

| Variable | Value |
|---|---|
| `{card_title}` | Card title |
| `{card_description}` | Card description |
| `{card_labels}` | Comma-separated labels |
| `{card_priority}` | Priority string |
| `{card_comments}` | All comments concatenated (includes previous agent outputs) |
| `{last_agent_output}` | Most recent agent comment on this card |
| `{column_name}` | Name of the column the card is in |
| `{board_name}` | Name of the board |

**Default prompt template** (used when `prompt_template` is empty):

```
You are a {agent_type} agent working on a kanban card.

## Card: {card_title}

{card_description}

## Previous Agent Output
{last_agent_output}

## Instructions
Perform your role as {agent_type}. Be thorough and specific.
If you are reviewing, clearly state APPROVED or REJECTED with reasoning.
```

**How the reviewer "rejects"**: The completion handler checks the agent output for keywords. If the output contains "REJECTED" or "FAILED" (case-insensitive), the task is marked as failed, and the card routes to `on_failure_column_id`. Otherwise it is a success. This is simple but effective and avoids structured output parsing.

---

## 9. Failure Modes & Mitigations

| Failure Mode | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Worker goes offline mid-task | Task stuck in 'running' forever | Medium | Server marks tasks as 'failed' if worker heartbeat expires while task is running. Stale detection runs every 60s. |
| kiro-cli hangs | Worker blocked, no new tasks processed | Medium | KiraClient has `timeout` (default 600s). Worker kills subprocess on timeout and reports failure. |
| Card moved manually while agent is running | Agent output applies to wrong column context | Low | Task stores `source_column_id`. On completion, verify card is still in expected column. If not, skip auto-move. |
| Loop count exceeded | Card stuck with failed status | By design | User sees the card with `agent_status='failed'` and must intervene. This is the expected circuit breaker. |
| SQLite write contention (multiple workers) | Slow writes, potential SQLITE_BUSY | Low (1 worker/user) | WAL mode already enabled. Task claim uses atomic UPDATE with WHERE status='pending'. Retry on SQLITE_BUSY. |
| Worker creates cards but fails to report completion | Orphaned cards without task completion | Low | Worker wraps card creation + completion report in a try/finally. Cards are visible immediately; worst case, task stays 'running' until heartbeat timeout. |
| Server restarts | In-memory SSE state lost | Medium | SSE clients reconnect automatically (existing retry logic in `useSSE.ts`). Workers re-register on next heartbeat failure. Tasks in DB are durable. |

---

## 10. Security Considerations

- **Jira credentials never reach the server.** Workers store and use credentials locally. The `users` table still has `jira_token_encrypted` but this is only used if the user explicitly saves via the web UI (PATCH /api/auth/users/me/jira). In the new model, workers use `~/.kira/jira.yaml` or env vars.
- **Worker authentication**: Workers use the same JWT as the frontend. No separate worker auth scheme needed.
- **Task assignment**: Tasks are assigned to a specific `user_id`. Workers can only poll tasks for their own user (enforced by JWT).
- **No server-side code execution**: Server never runs kiro-cli or calls Jira. It only manages state.
- **SQL injection**: All queries use parameterized statements (existing pattern).

---

## 11. Observability Plan

### Key Metrics
- `tasks_created_total` (by task_type)
- `tasks_completed_total` (by task_type, success/failure)
- `task_duration_seconds` (histogram, by task_type)
- `workers_online_count`
- `worker_heartbeat_age_seconds` (gauge per worker)
- `automation_loops_total` (by board_id, column_id)

### Logging
- Server: structured JSON logs for task lifecycle events (created, claimed, completed, failed).
- Worker: structured JSON logs for kiro-cli invocations, exit codes, durations.
- Both: request_id correlation via header propagation.

### Alerting
- Worker offline for > 5 minutes with pending tasks assigned to it.
- Task stuck in 'running' for > 15 minutes (kiro-cli timeout is 10 min).
- Loop count reaching max_loop_count (card is stuck).

---

## 12. Rollout Plan & Rollback

### Phase 1: Schema + Worker Backend (this PR)
1. Add `workers` and `tasks` tables via migration.
2. Implement worker protocol endpoints.
3. Implement automation trigger in `move_card()`.
4. Keep existing `agent_runs` table and endpoints alive (deprecated but functional).

### Phase 2: Worker Process
1. Create `src/kira/worker/` module.
2. Implement poll loop, kiro-cli execution, Jira execution.
3. CLI command: `kira worker start` or standalone script.

### Phase 3: Frontend Updates
1. Column configuration panel (agent settings).
2. Worker status indicator.
3. Remove WorkflowBuilder component.
4. Update agent/task status indicators.

### Phase 4: Cleanup
1. Remove deprecated `agent_runs` endpoints.
2. Drop `workflows` and `agent_runs` tables.
3. Delete legacy CLI modules.

### Rollback
- Phase 1 is additive only (new tables, new endpoints). Old code continues to work.
- If Phase 2 fails, workers are not deployed; users can still use the board manually without automation.
- Feature flag: `auto_run` on columns defaults to `false`. No automation fires until a user configures it.

---

## 13. Files to DELETE

### Legacy CLI modules (unused in kanban mode)

| Path | Reason |
|---|---|
| `src/kira/memory/` (entire directory) | CLI memory system, not used by web backend |
| `src/kira/skills/` (entire directory) | CLI skills system, not used by web backend |
| `src/kira/thinking/` (entire directory) | CLI deep reasoning, not used by web backend |
| `src/kira/workflows/` (entire directory) | CLI workflow orchestrator, replaced by board columns |
| `src/kira/correction/` (entire directory) | CLI self-correction loop, not used |
| `src/kira/context/` (entire directory) | CLI context analysis, not used |
| `src/kira/git/` (entire directory) | CLI git assistant, not used |
| `src/kira/logs/` (entire directory) | CLI run log storage, not used |
| `src/kira/tools/` (entire directory) | CLI tool system, not used |
| `src/kira/rules/` (entire directory) | CLI coding rules, not used |
| `src/kira/cli/commands/config.py` | CLI config command |
| `src/kira/cli/commands/logs.py` | CLI logs command |
| `src/kira/cli/commands/memory.py` | CLI memory command |
| `src/kira/cli/commands/skills.py` | CLI skills command |
| `src/kira/cli/repl.py` | CLI interactive REPL |
| `src/kira/cli/formatter.py` | CLI output formatter (if exists) |
| `src/kira/cli/output.py` | CLI output helpers (if exists) |
| `src/kira/core/agent.py` | CLI autonomous agent |
| `src/kira/core/config.py` | CLI-era config (replaced by web config) |
| `src/kira/core/defaults.py` | CLI-era defaults |
| `src/kira/core/models.py` | CLI model aliases (keep `resolve_model` if worker needs it -- see below) |
| `src/kira/core/personality.py` | CLI personality system |
| `src/kira/core/session.py` | CLI session manager |
| `src/kira/core/verifier.py` | CLI verification system |
| `src/kira/integrations/chalk/` (entire directory) | Chalk/Confluence integration not used by kanban |

### Web backend files to delete

| Path | Reason |
|---|---|
| `src/kira/web/agents/orchestrator.py` | Replaced by `src/kira/web/tasks/service.py` |
| `src/kira/web/agents/models.py` | Workflow models no longer needed; agent models restructured |
| `src/kira/web/agents/router.py` | Replaced by `src/kira/web/tasks/router.py` + `src/kira/web/workers/router.py` |
| `src/kira/web/jira/sync.py` | Jira operations move to worker; server only creates tasks |

### Frontend files to delete

| Path | Reason |
|---|---|
| `frontend/src/features/agents/WorkflowBuilder.tsx` | No workflow builder -- columns ARE the workflow |
| `frontend/src/features/agents/AgentRunner.tsx` | Replaced by column auto-run; no manual "Run Agent" dialog |

---

## 14. Files to CREATE

### Backend: Worker protocol

| Path | Purpose |
|---|---|
| `src/kira/web/workers/__init__.py` | Package init |
| `src/kira/web/workers/models.py` | Pydantic models: `WorkerRegister`, `WorkerHeartbeat`, `WorkerResponse`, `HeartbeatResponse` |
| `src/kira/web/workers/router.py` | Router: register, heartbeat, poll, claim, progress, complete, fail |
| `src/kira/web/workers/service.py` | Business logic: worker CRUD, stale detection, heartbeat processing |

### Backend: Task system

| Path | Purpose |
|---|---|
| `src/kira/web/tasks/__init__.py` | Package init |
| `src/kira/web/tasks/models.py` | Pydantic models: `TaskCreate`, `TaskResponse`, `TaskComplete`, `TaskFail`, `TaskProgress` |
| `src/kira/web/tasks/router.py` | Router: list tasks, cancel task (frontend-facing) |
| `src/kira/web/tasks/service.py` | Business logic: create task, update status, automation trigger |

### Backend: Automation

| Path | Purpose |
|---|---|
| `src/kira/web/automation/__init__.py` | Package init |
| `src/kira/web/automation/trigger.py` | `maybe_trigger()`: checks column config, creates task on card move |
| `src/kira/web/automation/prompt.py` | `render_prompt()`: renders column prompt_template with card data |
| `src/kira/web/automation/reviewer.py` | `detect_rejection()`: parses agent output for APPROVED/REJECTED |

### Worker process

| Path | Purpose |
|---|---|
| `src/kira/worker/__init__.py` | Package init |
| `src/kira/worker/config.py` | Worker configuration (server URL, poll interval, auth token) |
| `src/kira/worker/client.py` | HTTP client for server API (register, heartbeat, poll, claim, complete, fail) |
| `src/kira/worker/runner.py` | Main poll loop: poll -> claim -> execute -> report |
| `src/kira/worker/executors/__init__.py` | Package init for executors |
| `src/kira/worker/executors/agent.py` | Agent executor: runs kiro-cli via `KiraClient`, streams output |
| `src/kira/worker/executors/jira.py` | Jira executor: import, push, sync using local `JiraClient` |
| `src/kira/worker/cli.py` | CLI entry point: `kira worker start`, `kira worker status` |

### Frontend: New components

| Path | Purpose |
|---|---|
| `frontend/src/features/board/ColumnConfig.tsx` | Column settings panel: agent_type, auto_run, success/failure routing, prompt template, max loops |
| `frontend/src/features/board/TaskStatusBadge.tsx` | Badge showing task status on cards (pending/running/completed/failed) with progress text |
| `frontend/src/features/board/WorkerStatus.tsx` | Header indicator: shows which workers are online, task counts |
| `frontend/src/api/workers.ts` | API client for worker endpoints |
| `frontend/src/api/tasks.ts` | API client for task endpoints |
| `frontend/src/types/worker.ts` | TypeScript types: `Worker`, `WorkerStatus` |
| `frontend/src/types/task.ts` | TypeScript types: `Task`, `TaskType`, `TaskStatus` |
| `frontend/src/hooks/useWorkerStatus.ts` | Hook: polls worker status, shows online/offline |

---

## 15. Files to MODIFY

### Backend

| Path | Change |
|---|---|
| `src/kira/web/db/schema.sql` | Add `workers` and `tasks` tables. Remove `agent_runs` and `workflows` tables. |
| `src/kira/web/db/database.py` | Add migration logic for new tables. |
| `src/kira/web/db/seed.py` | Optionally seed columns with `auto_run` config for demo board. |
| `src/kira/web/app.py` | Register new routers (`workers_router`, `tasks_router`). Remove `agents_router`. Add stale worker detection background task on startup. |
| `src/kira/web/config.py` | No changes needed (all new config is in worker). |
| `src/kira/web/deps.py` | No changes needed. |
| `src/kira/web/cards/service.py` | `move_card()`: after moving, call `automation.trigger.maybe_trigger()`. |
| `src/kira/web/cards/models.py` | No changes needed. |
| `src/kira/web/cards/router.py` | No changes needed (move endpoint unchanged). |
| `src/kira/web/boards/service.py` | `get_full_board()`: include column automation fields in response (already there, but verify). |
| `src/kira/web/boards/router.py` | `get_board()`: pass automation fields through to `ColumnWithCards` (currently missing -- the router constructs `ColumnWithCards` without automation fields). |
| `src/kira/web/boards/models.py` | No changes needed (automation fields already on `ColumnWithCards`). |
| `src/kira/web/jira/router.py` | Change all endpoints to create tasks instead of calling Jira directly. Import, push, sync all return `{ task_id, status: "pending" }`. |
| `src/kira/web/jira/models.py` | Add `JiraTaskResponse` model. Keep existing models for reference. |
| `src/kira/web/events/models.py` | Add new event types: `TASK_CREATED`, `TASK_CLAIMED`, `TASK_COMPLETED`, `TASK_FAILED`, `WORKER_ONLINE`, `WORKER_OFFLINE`. |
| `src/kira/web/events/manager.py` | No changes needed. |
| `src/kira/web/events/router.py` | No changes needed. |
| `src/kira/__init__.py` | Remove lazy imports for `KiraAgent`, `AgentResult`, `Config`. Add `Worker` if we expose it. Simplify. |
| `src/kira/__main__.py` | Update if needed. |
| `src/kira/cli/app.py` | Strip down to just `serve` and `worker` commands. Remove `chat`, `memory`, `skills`, `config`, `logs`, `status`, `update`, `version` commands. Or keep `version` and `serve`. Add `worker start` subcommand. |
| `pyproject.toml` | Remove unused dependencies (`prompt-toolkit`). Keep `typer`, `rich`, `pyyaml`, `fastapi`, `uvicorn`, `aiosqlite`, `chromadb`, `sse-starlette`, `pyjwt`. Add `httpx` for worker HTTP client. |

### Frontend

| Path | Change |
|---|---|
| `frontend/src/types/board.ts` | Add automation fields to `Column` type: `agent_type`, `auto_run`, `on_success_column_id`, `on_failure_column_id`, `max_loop_count`, `prompt_template`, `agent_skill`, `agent_model`. Update `CreateColumnRequest` and `UpdateColumnRequest`. |
| `frontend/src/types/agent.ts` | Remove `Workflow`, `WorkflowStage`, `WorkflowLoop`, `CreateWorkflowRequest`. Keep `AgentSpec`, `AgentRun` (renamed/repurposed as `Task`). |
| `frontend/src/types/events.ts` | Add `TaskCreatedEvent`, `TaskClaimedEvent`, `TaskCompletedEvent`, `TaskFailedEvent`, `WorkerOnlineEvent`, `WorkerOfflineEvent`. |
| `frontend/src/api/agents.ts` | Remove workflow endpoints. Keep `fetchAvailableAgents`. Remove `runAgent` (automation handles this). |
| `frontend/src/api/boards.ts` | Update `createColumn` and `updateColumn` to include automation fields. |
| `frontend/src/api/jira.ts` | Update response types: all operations now return `{ task_id, status }` instead of direct results. |
| `frontend/src/stores/boardStore.ts` | No changes needed for core state. May add task-related state if needed. |
| `frontend/src/hooks/useSSE.ts` | Add handlers for new task/worker events. |
| `frontend/src/features/board/Column.tsx` | Add automation indicator (show agent icon if `auto_run` is true). Add column config gear icon. |
| `frontend/src/features/board/Card.tsx` | Show `TaskStatusBadge` based on `agent_status`. |
| `frontend/src/features/board/CardDetail.tsx` | Show task history (list of tasks for this card). Show agent output from comments. |
| `frontend/src/features/board/Board.tsx` | Remove `AgentRunner` and `WorkflowBuilder` imports. |
| `frontend/src/features/board/BoardHeader.tsx` | Add `WorkerStatus` component. |
| `frontend/src/features/agents/AgentPanel.tsx` | Repurpose as task output viewer. Update to use task API instead of agent run API. |
| `frontend/src/features/jira/JiraImport.tsx` | Update to show "task queued" instead of immediate results. |
| `frontend/src/features/jira/JiraSettings.tsx` | Add note about worker needing local credentials. |
| `frontend/src/components/layout/Header.tsx` | Add worker status indicator. |
| `frontend/src/App.tsx` | Remove `WorkflowBuilder` and `AgentRunner` from rendered components. |

---

## 16. Boards Router Bug Fix

The current `get_board()` in `/Users/P2799106/Projects/kira/src/kira/web/boards/router.py` (line 47-59) constructs `ColumnWithCards` without passing automation fields:

```python
columns = [
    ColumnWithCards(
        id=c["id"],
        board_id=c["board_id"],
        name=c["name"],
        position=c["position"],
        wip_limit=c["wip_limit"],
        color=c["color"],
        collapsed=c["collapsed"],
        cards=[CardBrief(**card) for card in c["cards"]],
    )
    for c in result["columns"]
]
```

This drops `agent_type`, `auto_run`, `on_success_column_id`, etc. Fix by passing all fields:

```python
columns = [
    ColumnWithCards(
        **{k: v for k, v in c.items() if k != "cards"},
        cards=[CardBrief(**card) for card in c["cards"]],
    )
    for c in result["columns"]
]
```

Similarly, `create_column()` in the boards service does not pass automation fields from the request body to the INSERT. This needs to be fixed to accept all `ColumnCreate` fields.

---

## 17. Acceptance Criteria

1. **Worker registration**: A worker process can register with the server and appear in the workers list.
2. **Worker heartbeat**: Worker heartbeat keeps it online. Missing heartbeats mark it stale/offline.
3. **Card move triggers task**: Moving a card to an `auto_run=true` column creates a `pending` task.
4. **Worker executes task**: Worker polls, claims, executes kiro-cli, and reports completion.
5. **Agent output stored as comment**: Completed task output appears as a card comment with `is_agent_output=true`.
6. **Auto-move on success**: After task completion, card moves to `on_success_column_id`.
7. **Auto-move on failure**: After task failure (or reviewer rejection), card moves to `on_failure_column_id`.
8. **Loop count enforced**: Card does not loop more than `max_loop_count` times through the same column.
9. **Jira operations as tasks**: Import, push, and sync create tasks instead of executing directly.
10. **Column config UI**: Frontend allows configuring agent_type, auto_run, success/failure columns, prompt template.
11. **Worker status visible**: Frontend shows which workers are online.
12. **SSE events for tasks**: Task lifecycle events stream to frontend in real time.
13. **No direct kiro-cli on server**: Server process never spawns kiro-cli or calls Jira API.
14. **Graceful worker shutdown**: Worker deregisters and in-flight tasks are marked failed with appropriate error.
