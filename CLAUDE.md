# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

kira is an agentic CLI and web app built on top of kiro-cli. It adds persistent memory (SQLite + FTS5), a skills/rules system, multi-phase deep reasoning, autonomous self-correction, and a real-time Kanban board web UI.

The CLI delegates all LLM interaction to kiro-cli via subprocess — prompts are sent through stdin in `--no-interactive` mode, and stdout is streamed back with ANSI/banner filtering (see `core/client.py` for ~30 filter patterns).

## Development Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run CLI
kira                              # Interactive REPL
kira chat "prompt"                # One-shot
kira serve                        # Start web backend (port 8000)

# Run full-stack (backend + React frontend)
./scripts/start.sh                # Requires Node 22 (nvm use 22)
./scripts/stop.sh

# Test
pytest                            # asyncio_mode = "auto" in config
pytest tests/test_foo.py          # Single file
pytest tests/test_foo.py::test_x  # Single test

# Lint
ruff check src/
ruff format src/

# Frontend (in frontend/)
npm install && npm run dev        # Dev server on port 5173
npm run build                     # Production build
```

## Architecture

The codebase has two main surfaces: a **CLI** (typer) and a **web backend** (FastAPI), sharing core logic.

### CLI Flow (`src/kira/cli/`)

`app.py` is the typer entry point. The `chat` command routes to one of four async runners based on flags:
- `_run_one_shot()` — default, sends prompt through `SessionManager.build_prompt()` → `KiraClient.run()`
- `_run_thinking()` — 7-phase deep reasoning via `DeepReasoning`, then executes refined plan
- `_run_autonomous()` — full pipeline: reasoning → execution → self-correction via `KiraAgent`
- `_run_workflow()` — multi-stage orchestration (architect → coder → reviewer → docs)

The `serve` command starts the FastAPI backend via uvicorn.

### Core Pipeline (`src/kira/core/`)

1. `Config.load()` merges `~/.kira/config.yaml` + `.kira/config.yaml`
2. `SessionManager` assembles the full prompt: personality + memory context + skills + rules + user prompt
3. `KiraClient` spawns kiro-cli subprocess, streams stdout, filters ANSI/banners line-by-line
4. Response is scanned for `[REMEMBER:key]` and `[PROJECT:key]` markers → auto-extracted to memory

Key files:
- `client.py` — subprocess wrapper, ANSI filtering, `run()` yields async chunks
- `session.py` — prompt assembly, memory injection, marker extraction
- `agent.py` — `KiraAgent` for autonomous mode (reasoning + correction loop)
- `models.py` — model alias resolution (fast→haiku, smart→sonnet, best→opus)

### Web Backend (`src/kira/web/`)

FastAPI app factory pattern in `app.py` with lifespan that inits SQLite + ChromaDB.

Routers: `auth` (JWT), `boards`, `cards`, `events` (SSE real-time), `jira` (bidirectional sync), `search` (ChromaDB + SQL fallback), `agents` (AI workflow orchestration).

Each feature follows the pattern: `router.py` (endpoints) → `service.py` (business logic) → `models.py` (Pydantic).

Database: aiosqlite with migrations in `web/db/migrations/`. Demo data seeded on first run via `seed.py`.

### Frontend (`frontend/`)

React 19 + TypeScript + Vite 7. State management via Zustand, data fetching via TanStack Query, drag-and-drop via dnd-kit. Requires Node 22.

### Other Subsystems

- **Memory** (`memory/`) — SQLite + FTS5 with decay (5%/week), relevance scoring, auto-extraction, failure learning
- **Thinking** (`thinking/`) — 7-phase reasoning: UNDERSTAND → EXPLORE → ANALYZE → PLAN → CRITIQUE → REFINE → VERIFY, then execute. Adaptive: trivial tasks skip phases. Loops back to EXPLORE if confidence < 50%
- **Correction** (`correction/`) — `SelfCorrector` with `FailureAnalyzer` + `PlanReviser`, max 3 retries
- **Skills** (`skills/`) — YAML files loaded from builtin → `~/.kira/skills/` → `.kira/skills/`
- **Rules** (`rules/`) — Auto-injected by keyword triggers (e.g., "refactor" → refactoring.yaml). Priority: project → user → builtin
- **Integrations** (`integrations/`) — Jira REST v2 client, Chalk API client
- **Context** (`context/`) — `SmartContextLoader` auto-detects relevant files from task description
- **Workflows** (`workflows/`) — `WorkflowOrchestrator` runs multi-stage workflows via `AgentSpawner`

## Key Patterns

- **All I/O is async**: aiosqlite, asyncio subprocess, FastAPI async handlers. CLI uses `asyncio.run()` at the boundary.
- **Prompt assembly order**: personality → memory context → project memory → skill prompts → rules → smart context → user prompt (see `SessionManager.build_prompt()`)
- **kiro-cli invocation**: `kiro-cli chat --no-interactive --wrap never --trust-all-tools [--model MODEL]` — prompt via stdin, not args.
- **Output filtering**: `KiraClient._clean_line()` applies ~30 regex patterns to strip kiro-cli chrome. If kiro-cli output format changes, these patterns need updating.
- **Memory markers**: `[REMEMBER:key] content` → personal memory (`~/.kira/memory.db`), `[PROJECT:key] content` → team memory (`.kira/project-memory.yaml`).

## Configuration

- User config: `~/.kira/config.yaml`
- Project config: `.kira/config.yaml` (overrides user)
- User memory DB: `~/.kira/memory.db`
- Project memory: `.kira/project-memory.yaml` (git-tracked)
- Kanban DB: `.kira/kanban.db` (local only)
- Ruff: line-length 100, target py312, select E/F/I/UP/B/SIM
