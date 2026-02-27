# Kira Kanban Board - System Architecture

## Overview

A real-time, AI-powered Kanban board with bidirectional Jira sync. Built as a client/server application for internal teams (5-20 users).

```
┌─────────────────────────────────────────────────────────────────┐
│                    React + TypeScript Frontend                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │
│  │  Kanban   │ │   Card   │ │   Jira   │ │  Agent Workflow   │  │
│  │  Board    │ │  Detail  │ │  Sync UI │ │  Builder & Runner │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬──────────┘  │
│       │             │            │                 │              │
│  ┌────┴─────────────┴────────────┴─────────────────┴──────────┐  │
│  │              Zustand Store + TanStack Query                 │  │
│  │              SSE Connection (EventSource)                   │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
└────────────────────────────┼─────────────────────────────────────┘
                             │ HTTP + SSE
┌────────────────────────────┼─────────────────────────────────────┐
│                    FastAPI Backend                                │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐  │
│  │ Board   │ │ Card    │ │  SSE    │ │  Jira    │ │ Agent   │  │
│  │ Routes  │ │ Routes  │ │ Stream  │ │  Sync    │ │ Routes  │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬─────┘ └────┬────┘  │
│       │           │           │            │             │        │
│  ┌────┴───────────┴───────────┴────────────┴─────────────┴────┐  │
│  │                    Service Layer                             │  │
│  │  BoardService │ CardService │ JiraSync │ AgentOrchestrator  │  │
│  └────────┬──────────────┬─────────────────────┬──────────────┘  │
│           │              │                     │                  │
│  ┌────────┴──────┐ ┌─────┴──────┐ ┌───────────┴───────────────┐ │
│  │   SQLite      │ │  ChromaDB  │ │  Kira Integration Layer   │ │
│  │   (aiosqlite) │ │  (vectors) │ │  (JiraClient, Agents)     │ │
│  └───────────────┘ └────────────┘ └───────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## Tech Stack

### Backend
- **FastAPI** - Async API framework with SSE support
- **aiosqlite** - Async SQLite for relational data
- **ChromaDB** - Vector database for semantic search
- **sse-starlette** - Server-Sent Events
- **PyJWT** - JWT token generation/validation
- **uvicorn** - ASGI server

### Frontend
- **Vite** - Build tool
- **React 18** - UI framework
- **TypeScript** - Type safety
- **TailwindCSS** - Utility-first styling
- **Framer Motion** - Animations and transitions
- **@dnd-kit** - Drag and drop
- **Zustand** - State management
- **TanStack Query** - Server state and caching

---

## Directory Structure

```
src/kira/web/
├── __init__.py
├── app.py                      # FastAPI app factory
├── config.py                   # Web server settings
├── deps.py                     # Dependency injection
│
├── auth/
│   ├── __init__.py
│   ├── router.py               # POST /login, GET /me
│   ├── service.py              # Mock auth + JWT
│   └── models.py               # User, Token, LoginRequest
│
├── boards/
│   ├── __init__.py
│   ├── router.py               # CRUD /boards, /boards/{id}/full
│   ├── service.py              # Board business logic
│   └── models.py               # Board, Column, BoardMember
│
├── cards/
│   ├── __init__.py
│   ├── router.py               # CRUD /cards, move, reorder
│   ├── service.py              # Card business logic
│   └── models.py               # Card, CardComment, CardActivity
│
├── events/
│   ├── __init__.py
│   ├── router.py               # GET /events/stream (SSE)
│   ├── manager.py              # EventManager (pub/sub)
│   └── models.py               # Event types
│
├── jira/
│   ├── __init__.py
│   ├── router.py               # /jira/sync, /jira/import, /jira/push
│   ├── sync.py                 # JiraSyncService (bidirectional)
│   └── models.py               # SyncStatus, SyncConfig, FieldMapping
│
├── agents/
│   ├── __init__.py
│   ├── router.py               # POST /agents/run, GET /agents/status
│   ├── orchestrator.py         # AgentWorkflowOrchestrator
│   └── models.py               # WorkflowConfig, AgentRun
│
├── search/
│   ├── __init__.py
│   ├── router.py               # GET /search
│   └── service.py              # ChromaDB + FTS hybrid search
│
└── db/
    ├── __init__.py
    ├── database.py             # SQLite connection manager
    ├── schema.sql              # Full schema
    ├── seed.py                 # Demo data
    └── migrations/             # Schema migrations

frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   ├── client.ts           # Axios/fetch wrapper
│   │   ├── boards.ts           # Board API calls
│   │   ├── cards.ts            # Card API calls
│   │   ├── jira.ts             # Jira API calls
│   │   └── agents.ts           # Agent API calls
│   ├── components/
│   │   ├── ui/                 # Shared UI primitives
│   │   │   ├── Button.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Avatar.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Dropdown.tsx
│   │   │   └── Toast.tsx
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── Layout.tsx
│   │   └── shared/
│   │       ├── SearchPalette.tsx    # Cmd+K search
│   │       └── AgentStream.tsx     # Agent output renderer
│   ├── features/
│   │   ├── board/
│   │   │   ├── Board.tsx           # Main board view
│   │   │   ├── Column.tsx          # Kanban column
│   │   │   ├── Card.tsx            # Kanban card
│   │   │   ├── CardDetail.tsx      # Card detail slide-over
│   │   │   ├── NewCard.tsx         # Inline card creation
│   │   │   ├── BoardHeader.tsx     # Board title, filters, actions
│   │   │   └── WipIndicator.tsx    # WIP limit indicator
│   │   ├── auth/
│   │   │   ├── Login.tsx           # Login page
│   │   │   └── UserMenu.tsx        # User dropdown
│   │   ├── jira/
│   │   │   ├── JiraSettings.tsx    # Jira config panel
│   │   │   ├── JiraImport.tsx      # Import wizard
│   │   │   └── JiraBadge.tsx       # Sync status badge
│   │   └── agents/
│   │       ├── WorkflowBuilder.tsx # Visual workflow editor
│   │       ├── AgentRunner.tsx     # Run agent on card
│   │       └── AgentPanel.tsx      # Agent output panel
│   ├── hooks/
│   │   ├── useSSE.ts              # SSE connection hook
│   │   ├── useBoard.ts            # Board data hook
│   │   ├── useDragDrop.ts         # DnD hook wrapper
│   │   └── useKeyboard.ts         # Keyboard shortcuts
│   ├── stores/
│   │   ├── boardStore.ts          # Board state
│   │   ├── authStore.ts           # Auth state
│   │   └── uiStore.ts             # UI state (modals, panels)
│   ├── types/
│   │   ├── board.ts               # Board, Column, Card types
│   │   ├── user.ts                # User types
│   │   ├── jira.ts                # Jira types
│   │   └── agent.ts               # Agent types
│   └── styles/
│       └── globals.css            # Tailwind base + custom
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## Database Schema

### SQLite (Relational Data)

```sql
-- Users (mock auth for now)
CREATE TABLE users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT DEFAULT '',
    jira_username TEXT DEFAULT '',
    jira_server TEXT DEFAULT '',
    jira_token_encrypted TEXT DEFAULT '',
    preferences_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Boards
CREATE TABLE boards (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner_id TEXT NOT NULL REFERENCES users(id),
    jira_project_key TEXT DEFAULT '',
    jira_sync_enabled INTEGER DEFAULT 0,
    jira_sync_jql TEXT DEFAULT '',
    settings_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Board members
CREATE TABLE board_members (
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    PRIMARY KEY (board_id, user_id)
);

-- Columns
CREATE TABLE columns (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    wip_limit INTEGER DEFAULT 0,
    color TEXT DEFAULT '#6366f1',
    collapsed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cards
CREATE TABLE cards (
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

-- Card comments
CREATE TABLE card_comments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    is_agent_output INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Card activity log
CREATE TABLE card_activity (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent runs
CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    card_id TEXT REFERENCES cards(id) ON DELETE SET NULL,
    board_id TEXT NOT NULL REFERENCES boards(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    agent_type TEXT NOT NULL,
    workflow_name TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    input_text TEXT DEFAULT '',
    output_text TEXT DEFAULT '',
    error_text TEXT DEFAULT '',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workflow definitions
CREATE TABLE workflows (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    board_id TEXT REFERENCES boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    stages_json TEXT NOT NULL DEFAULT '[]',
    trigger_column_id TEXT REFERENCES columns(id),
    loop_enabled INTEGER DEFAULT 0,
    loop_max_iterations INTEGER DEFAULT 3,
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_cards_column ON cards(column_id, position);
CREATE INDEX idx_cards_board ON cards(board_id);
CREATE INDEX idx_cards_jira ON cards(jira_key) WHERE jira_key != '';
CREATE INDEX idx_columns_board ON columns(board_id, position);
CREATE INDEX idx_comments_card ON card_comments(card_id, created_at);
CREATE INDEX idx_activity_card ON card_activity(card_id, created_at);
CREATE INDEX idx_agent_runs_card ON agent_runs(card_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status) WHERE status = 'running';
```

### ChromaDB (Vector Search)

```
Collection: kira_cards
  - id: card_id
  - document: "{title}\n{description}"
  - metadata: {board_id, column_id, priority, labels, assignee_id}

Collection: kira_comments
  - id: comment_id
  - document: comment content
  - metadata: {card_id, board_id, user_id, is_agent_output}
```

---

## API Contract

### Authentication
```
POST   /api/auth/login          # { username } → { token, user }
GET    /api/auth/me              # → { user }
```

### Boards
```
GET    /api/boards               # → [Board]
POST   /api/boards               # { name, description } → Board
GET    /api/boards/{id}          # → Board (with columns and cards)
PATCH  /api/boards/{id}          # { name?, description?, settings? } → Board
DELETE /api/boards/{id}          # → 204
```

### Columns
```
POST   /api/boards/{id}/columns           # { name, color?, wip_limit? } → Column
PATCH  /api/columns/{id}                  # { name?, color?, wip_limit? } → Column
DELETE /api/columns/{id}                  # → 204
PATCH  /api/boards/{id}/columns/reorder   # { column_ids: [] } → 200
```

### Cards
```
GET    /api/cards/{id}                    # → Card (full detail)
POST   /api/cards                         # { column_id, title, ... } → Card
PATCH  /api/cards/{id}                    # { title?, description?, ... } → Card
DELETE /api/cards/{id}                    # → 204
POST   /api/cards/{id}/move               # { column_id, position } → Card
POST   /api/cards/reorder                 # { column_id, card_ids: [] } → 200
```

### Comments
```
GET    /api/cards/{id}/comments           # → [Comment]
POST   /api/cards/{id}/comments           # { content } → Comment
DELETE /api/comments/{id}                 # → 204
```

### SSE Events
```
GET    /api/events/stream?board_id={id}   # SSE stream
  → event: card_created      data: { card }
  → event: card_moved        data: { card_id, from_column, to_column, position }
  → event: card_updated      data: { card }
  → event: card_deleted      data: { card_id }
  → event: column_created    data: { column }
  → event: column_reordered  data: { column_ids }
  → event: comment_added     data: { comment }
  → event: agent_started     data: { agent_run }
  → event: agent_progress    data: { agent_run_id, chunk }
  → event: agent_completed   data: { agent_run }
  → event: jira_synced       data: { card_id, jira_key, status }
  → event: user_presence     data: { user_id, action }
  → event: heartbeat         data: { timestamp }
```

### Jira
```
POST   /api/jira/test-connection          # → { success, user }
POST   /api/jira/import                   # { jql, board_id, column_id } → [Card]
POST   /api/jira/push/{card_id}           # → { jira_key, browse_url }
POST   /api/jira/sync/{board_id}          # → { synced, created, updated, conflicts }
GET    /api/jira/projects                 # → [JiraProject]
PATCH  /api/users/me/jira                 # { server, username, token } → 200
```

### Agents
```
GET    /api/agents/available              # → [AgentSpec] (from registry)
GET    /api/agents/workflows              # → [Workflow]
POST   /api/agents/workflows              # { name, stages, ... } → Workflow
POST   /api/agents/run                    # { card_id, agent_type?, workflow_id? } → AgentRun
GET    /api/agents/runs/{id}              # → AgentRun (with output)
POST   /api/agents/runs/{id}/cancel       # → 200
```

### Search
```
GET    /api/search?q={query}&board_id={id}  # → [SearchResult] (hybrid vector+FTS)
```

---

## SSE Event System

### Architecture

```
┌──────────┐     publish      ┌──────────────┐     SSE stream      ┌──────────┐
│  Service  │ ──────────────→ │ EventManager  │ ─────────────────→  │  Client  │
│  Layer    │                 │  (pub/sub)    │                     │  Browser │
└──────────┘                  │               │                     └──────────┘
                              │  Channels:    │
                              │  board:{id}   │
                              │  user:{id}    │
                              │  global       │
                              └──────────────┘
```

### EventManager

```python
class EventManager:
    """In-memory pub/sub for SSE events."""

    def __init__(self):
        self._channels: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._channels[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        self._channels[channel].discard(queue)

    async def publish(self, channel: str, event: Event):
        for queue in self._channels[channel]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop oldest if full
```

---

## Jira Bidirectional Sync

### Sync Flow

```
Import from Jira:
  1. User configures JQL filter per board (e.g., "project = PROJ AND sprint in openSprints()")
  2. Server queries Jira via existing JiraClient (using user's credentials)
  3. Maps Jira fields → Card fields
  4. Creates cards, sets jira_key, jira_sync_status = 'synced'
  5. Indexes card content in ChromaDB
  6. Broadcasts SSE events

Push to Jira:
  1. User clicks "Push to Jira" on a card (or auto-push on column change)
  2. Server creates/updates Jira issue via JiraClient
  3. Updates card.jira_key and jira_sync_status
  4. Optionally transitions Jira issue based on column mapping

Periodic Sync:
  1. Background task runs every N minutes (configurable per board)
  2. Fetches Jira issues matching JQL
  3. Compares with local cards by jira_key
  4. Updates whichever side is stale (last_modified wins)
  5. Flags conflicts for user resolution

Field Mapping:
  Jira summary     ↔ Card title
  Jira description ↔ Card description
  Jira status      ↔ Card column (configurable mapping)
  Jira assignee    ↔ Card assignee (by jira_username)
  Jira priority    ↔ Card priority
  Jira labels      ↔ Card labels
```

---

## Agent Workflow Execution

### Model: User's kiro-cli executes, server coordinates

```
┌──────────┐    1. trigger     ┌──────────────┐    2. SSE task    ┌──────────┐
│  Browser  │ ───────────────→ │   Server     │ ───────────────→  │ User's   │
│  (React)  │                  │  (FastAPI)   │                   │ kiro-cli │
│           │ ←──────────────  │              │ ←───────────────  │ instance │
│           │  5. SSE results  │              │  3. output stream │          │
└──────────┘                   └──────────────┘                   └──────────┘
                                     │
                                     │ 4. store results
                                     ↓
                               ┌──────────┐
                               │  SQLite   │
                               └──────────┘
```

### Workflow Definition (stages_json)

```json
{
  "stages": [
    {
      "name": "architect",
      "agent": "architect",
      "skill": "architect",
      "model": "smart",
      "prompt_template": "Design: {card_title}\n\n{card_description}"
    },
    {
      "name": "coder",
      "agent": "coder",
      "skill": "coder",
      "model": "best",
      "prompt_template": "{card_title}\n\nArchitecture:\n{architect_output}",
      "depends_on": "architect"
    },
    {
      "name": "reviewer",
      "agent": "reviewer",
      "skill": "reviewer",
      "model": "smart",
      "prompt_template": "Review:\n{coder_output}",
      "depends_on": "coder",
      "required": false
    }
  ],
  "loop": {
    "enabled": false,
    "condition": "reviewer rejects",
    "max_iterations": 3,
    "loop_stages": ["coder", "reviewer"]
  }
}
```

---

## Design Language

### Theme: "Obsidian Glass"

Dark-first design with glass-morphism, inspired by Linear + Raycast.

```
Background:     #0a0a0f (near-black with blue undertone)
Surface:        rgba(255, 255, 255, 0.03) + backdrop-blur
Card:           rgba(255, 255, 255, 0.05) + 1px border rgba(255,255,255,0.08)
Card Hover:     rgba(255, 255, 255, 0.08)
Text Primary:   #e2e8f0
Text Secondary: #64748b
Accent:         #818cf8 (indigo-400)
Success:        #34d399
Warning:        #fbbf24
Error:          #f87171
Jira Blue:      #2684ff

Priority Colors:
  critical: #ef4444 (red)
  high:     #f97316 (orange)
  medium:   #eab308 (yellow)
  low:      #22c55e (green)
  none:     #64748b (gray)
```

### Animation Principles
- Cards: spring physics on drag (stiffness: 300, damping: 30)
- Columns: smooth reflow on card enter/leave (layout animation)
- Modals: scale + fade in (0.2s ease-out)
- Toasts: slide in from top-right
- Agent output: typewriter effect for streaming text

### Key UI Patterns
- **Command Palette** (Cmd+K): Search cards, switch boards, run agents
- **Slide-over Panel**: Card detail opens as right panel (not modal)
- **Inline Editing**: Click card title to edit in-place
- **Drag Ghost**: Semi-transparent card clone follows cursor
- **Column Glow**: Subtle glow when dragging card over valid column
- **Agent Pulse**: Animated ring around card when agent is running
