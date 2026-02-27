-- Kira Kanban Board - Database Schema

-- Users (mock auth for now)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT DEFAULT '',
    preferences_json TEXT DEFAULT '{}',
    gitlab_server TEXT DEFAULT '',
    gitlab_token_encrypted TEXT DEFAULT '',
    centauth_sub TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Boards
CREATE TABLE IF NOT EXISTS boards (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner_id TEXT NOT NULL REFERENCES users(id),
    settings_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Board members
CREATE TABLE IF NOT EXISTS board_members (
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    PRIMARY KEY (board_id, user_id)
);

-- Columns (each column optionally triggers an agent when a card enters)
CREATE TABLE IF NOT EXISTS columns (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    wip_limit INTEGER DEFAULT 0,
    color TEXT DEFAULT '#6366f1',
    collapsed INTEGER DEFAULT 0,
    -- Workflow automation: the board IS the workflow
    agent_type TEXT DEFAULT '',
    agent_skill TEXT DEFAULT '',
    agent_model TEXT DEFAULT 'smart',
    auto_run INTEGER DEFAULT 0,
    on_success_column_id TEXT DEFAULT '',
    on_failure_column_id TEXT DEFAULT '',
    max_loop_count INTEGER DEFAULT 3,
    prompt_template TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cards
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    column_id TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    assignee_id TEXT REFERENCES users(id),
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('critical', 'high', 'medium', 'low', 'none')),
    labels TEXT DEFAULT '[]',
    due_date TEXT,
    jira_key TEXT DEFAULT '',
    jira_sync_status TEXT DEFAULT '' CHECK (jira_sync_status IN ('', 'synced', 'pending', 'conflict', 'error')),
    jira_last_synced TIMESTAMP,
    agent_status TEXT DEFAULT '' CHECK (agent_status IN ('', 'pending', 'running', 'completed', 'failed')),
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Card comments (also stores agent output)
CREATE TABLE IF NOT EXISTS card_comments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    is_agent_output INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Card activity log
CREATE TABLE IF NOT EXISTS card_activity (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workers: one per user, tracks local worker process status
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hostname TEXT NOT NULL DEFAULT '',
    worker_version TEXT NOT NULL DEFAULT '',
    capabilities_json TEXT NOT NULL DEFAULT '["agent"]',
    status TEXT NOT NULL DEFAULT 'online' CHECK (status IN ('online', 'offline', 'stale')),
    last_heartbeat TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

-- Tasks: unified queue for agent runs and jira operations
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    task_type TEXT NOT NULL CHECK (task_type IN (
        'agent_run', 'jira_import', 'jira_push', 'jira_sync',
        'gitlab_link', 'gitlab_create_project', 'gitlab_push',
        'board_plan', 'card_gen'
    )),
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    assigned_to TEXT REFERENCES users(id),
    claimed_by_worker TEXT REFERENCES workers(id),
    -- Agent fields
    agent_type TEXT DEFAULT '',
    agent_skill TEXT DEFAULT '',
    agent_model TEXT DEFAULT 'smart',
    prompt_text TEXT DEFAULT '',
    -- Integration payload (Jira, GitLab, etc.)
    payload_json TEXT DEFAULT '{}',
    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'claimed', 'running', 'completed', 'failed', 'cancelled'
    )),
    priority INTEGER NOT NULL DEFAULT 0,
    -- Automation routing
    source_column_id TEXT DEFAULT '',
    target_column_id TEXT DEFAULT '',
    failure_column_id TEXT DEFAULT '',
    loop_count INTEGER DEFAULT 0,
    max_loop_count INTEGER DEFAULT 3,
    -- Results
    error_summary TEXT DEFAULT '',
    output_comment_id TEXT DEFAULT '',
    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cards_column ON cards(column_id, position);
CREATE INDEX IF NOT EXISTS idx_cards_board ON cards(board_id);
CREATE INDEX IF NOT EXISTS idx_cards_jira ON cards(jira_key) WHERE jira_key != '';
CREATE INDEX IF NOT EXISTS idx_columns_board ON columns(board_id, position);
CREATE INDEX IF NOT EXISTS idx_comments_card ON card_comments(card_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_card ON card_activity(card_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_poll ON tasks(assigned_to, status) WHERE status IN ('pending', 'claimed');
CREATE INDEX IF NOT EXISTS idx_tasks_board ON tasks(board_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_card ON tasks(card_id) WHERE card_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, created_at) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_workers_user ON workers(user_id);
