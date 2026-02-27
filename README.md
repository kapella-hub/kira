# Kira

AI-powered Kanban board with local agent workers.

## What It Does

Kira is a real-time Kanban board where columns can have AI agents attached. When a card enters an agent-enabled column, the agent picks up the work automatically -- moving cards through your workflow without manual intervention.

- **Kanban board** with drag-and-drop, real-time SSE updates, search (ChromaDB + SQL fallback)
- **Agent columns** that trigger AI execution when cards land in them
- **Local workers** that run on user machines, poll the server for tasks, and execute them using local tools (kiro-cli, Jira, GitLab)
- **Jira bidirectional sync** -- import from and push to Jira
- **GitLab integration** -- per-user credentials, linked to cards
- **Authentication** -- mock mode (pick a username) or CentAuth SSO

## Architecture

```
Browser (React SPA)
    |
    | HTTP / SSE
    v
+-------------------+          +---------------------+
|  Frontend (nginx)  |  proxy  |  Backend (FastAPI)   |
|  :80               |-------->|  :8000               |
+-------------------+          |                      |
                               |  SQLite (kanban.db)  |
                               |  ChromaDB (optional)  |
                               +----------+-----------+
                                          |
                                   task queue
                                   (poll/claim)
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
              +-----+------+       +-----+------+       +-----+------+
              |  Worker A   |       |  Worker B   |       |  Worker C   |
              |  (alice)    |       |  (bob)      |       |  (charlie)  |
              |  localhost  |       |  laptop     |       |  CI runner  |
              +-------------+       +-------------+       +-------------+
```

**Backend** -- FastAPI app serving the REST API, SSE event stream, and the agent install endpoint. SQLite for persistence, ChromaDB for semantic search (optional, falls back to SQL LIKE).

**Frontend** -- React 19 SPA served by nginx. Communicates with the backend via `/api/` proxy. All client-side routing with SPA fallback.

**Workers** -- Lightweight daemons running on user machines. Each worker authenticates, registers with the server, then polls for tasks. When a task is claimed, the worker executes it locally (using kiro-cli, Jira API, GitLab API, etc.) and reports results back.

## Quick Start (Docker)

**Prerequisites:** Docker and Docker Compose.

```bash
# Clone and start
git clone <repository-url> && cd kira
docker compose up --build -d
```

The board is available at **http://localhost**. The API is at **http://localhost:8000** (docs at `/docs`).

In mock auth mode (the default), pick any username to log in -- no password required. Demo users `alice`, `bob`, and `charlie` are pre-seeded.

### Start a Worker

Workers run on your machine, outside Docker. Install the `kira` package first (see [Agent Installation](#agent-installation)), then:

```bash
kira worker --server http://localhost:8000
```

The worker prompts for your username (and password, if CentAuth is enabled). It registers, sends heartbeats, and polls for tasks.

## Development

**Prerequisites:** Python 3.12+, Node 22 (via nvm).

### Backend + Frontend (dev servers)

```bash
# Setup Python environment
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start both servers (backend :8000, frontend :5173)
./scripts/start.sh

# Or start with a worker attached
./scripts/start.sh alice

# Stop everything
./scripts/stop.sh
```

The start script launches:
- Backend on **http://localhost:8000** (uvicorn with `--reload`)
- Frontend on **http://localhost:5173** (Vite dev server)
- Worker (optional, if username argument provided)

Logs are written to `.logs/backend.log`, `.logs/frontend.log`, `.logs/worker.log`.

### Backend Only

```bash
kira serve --reload
```

### Frontend Only

```bash
cd frontend
npm install
npm run dev
```

### Tests and Linting

```bash
pytest                          # All tests (asyncio_mode = "auto")
pytest tests/test_foo.py        # Single file
ruff check src/                 # Lint
ruff format src/                # Format
```

## Configuration

All configuration is via environment variables. Set them in `.env` (Docker Compose reads this automatically) or export them in your shell.

| Variable | Default | Description |
|---|---|---|
| `KIRA_AUTH_MODE` | `mock` | `mock` (pick any username) or `centauth` (SSO) |
| `KIRA_JWT_SECRET` | dev default | **Change in production.** Secret for signing JWT tokens. |
| `KIRA_DB_PATH` | `.kira/kanban.db` | Path to the SQLite database |
| `KIRA_CHROMADB_PATH` | `.kira/chromadb` | Path to ChromaDB storage (optional) |
| `KIRA_CORS_ORIGINS` | localhost variants | Comma-separated allowed origins |
| `KIRA_DEBUG` | `false` | Enable debug mode |
| `KIRA_HOST` | `0.0.0.0` | Host to bind the backend to |
| `KIRA_PORT` | `8000` | Port for the backend |
| `KIRA_CENTAUTH_URL` | (empty) | CentAuth server URL (required if `auth_mode=centauth`) |
| `KIRA_CENTAUTH_APP_NAME` | `kira` | App name registered in CentAuth |
| `KIRA_CENTAUTH_VERIFY_SSL` | `true` | Verify SSL when connecting to CentAuth |

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

## Agent Installation

The running Kira server hosts a self-install script. Users on any machine with Python 3.12+ can install the agent with a single command:

```bash
curl -sSL http://your-kira-server/api/agent/install.sh | bash
```

This script:
1. Checks for Python 3.12+
2. Creates a virtualenv at `~/.kira/venv`
3. Downloads the `kira` wheel from the server (`/api/agent/package`)
4. Installs it and symlinks `kira` to `~/.local/bin/kira`
5. Installs a system service (launchd on macOS, systemd on Linux)
6. Starts the agent daemon

The agent is idempotent -- running the script again upgrades if a new version is available, or starts the agent if already installed.

On macOS, a `.command` file (double-clickable) is also available at `/api/agent/install.command`.

### Agent Commands

```bash
kira agent start       # Start the agent daemon
kira agent install     # Install as system service (auto-starts on login)
kira agent uninstall   # Remove system service
kira agent status      # Show agent status
```

### Worker Commands

```bash
kira worker                                          # Connect to localhost:8000
kira worker --server http://kira.internal:8000       # Connect to remote server
kira worker --user alice --password secret            # Non-interactive auth
```

## Project Structure

```
src/kira/
  cli/              CLI entry point (typer): serve, worker, agent, version
  web/              FastAPI backend
    auth/           Authentication (mock + CentAuth SSO)
    boards/         Board CRUD
    cards/          Card operations
    tasks/          Task queue (pending -> claimed -> complete/failed)
    workers/        Worker registration, heartbeat, task polling
    events/         SSE real-time event stream
    jira/           Jira bidirectional sync
    gitlab/         GitLab integration
    search/         ChromaDB + SQL fallback search
    agent_install/  Serves install script and wheel for remote agents
    db/             SQLite init, migrations, seed data
  worker/           Worker daemon (polls server, executes tasks locally)
  agent/            Agent daemon (browser-activated via WebSocket)
  integrations/     Jira REST v2 client, Chalk API client
  core/             Shared models, config, kiro-cli client
frontend/           React 19 + TypeScript + Vite 7
scripts/            Dev helper scripts (start, stop, restart, docker)
docker/             nginx.conf for the frontend container
```

## Tech Stack

**Backend:** Python 3.12, FastAPI, uvicorn, aiosqlite, PyJWT, httpx, sse-starlette, websockets

**Frontend:** React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, Zustand, TanStack Query, dnd-kit, Framer Motion, React Router 7

**Infrastructure:** Docker (multi-stage build), nginx, SQLite, ChromaDB (optional)

## License

MIT
