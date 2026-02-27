"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import WebConfig


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Run lightweight schema migrations."""
    # Add centauth_sub column to users table if missing
    cursor = await db.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "centauth_sub" not in columns:
        await db.execute("ALTER TABLE users ADD COLUMN centauth_sub TEXT DEFAULT ''")
        await db.commit()


async def _stale_worker_loop() -> None:
    """Background loop that marks stale/offline workers every 60 seconds."""
    from .db.database import get_db
    from .workers.service import mark_stale_workers

    while True:
        await asyncio.sleep(60)
        try:
            db = await get_db()
            await mark_stale_workers(db)
        except Exception:
            pass  # Best-effort; will retry next cycle


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: init DB, seed, init ChromaDB, start background tasks."""
    config = WebConfig.load()

    # Init SQLite
    from .db.database import close_db, init_db

    await init_db(config.db_path)

    # Seed demo data
    from .db.database import get_db
    from .db.seed import seed_db

    db = await get_db()
    await seed_db(db)

    # Run database migrations
    await _run_migrations(db)

    # Init auth provider
    from .auth.service import init_provider

    init_provider(config)

    # Init ChromaDB
    try:
        from .search.service import init_chromadb

        init_chromadb(config.chromadb_path)
    except Exception:
        # ChromaDB is optional - search falls back to SQL LIKE
        pass

    # Start background task for stale worker detection
    stale_task = asyncio.create_task(_stale_worker_loop())

    yield

    stale_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await stale_task

    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = WebConfig.load()

    app = FastAPI(
        title="Kira Kanban Board",
        description="Real-time AI-powered Kanban board with Jira sync",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    origins = config.cors_origins or [
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from .agent_install.router import router as agent_install_router
    from .auth.router import router as auth_router
    from .boards.router import router as boards_router
    from .cards.router import router as cards_router
    from .events.router import router as events_router
    from .gitlab.router import router as gitlab_router
    from .jira.router import router as jira_router
    from .search.router import router as search_router
    from .tasks.router import router as tasks_router
    from .workers.router import router as workers_router

    app.include_router(agent_install_router)
    app.include_router(auth_router)
    app.include_router(boards_router)
    app.include_router(cards_router)
    app.include_router(events_router)
    app.include_router(gitlab_router)
    app.include_router(jira_router)
    app.include_router(search_router)
    app.include_router(workers_router)
    app.include_router(tasks_router)

    # Error handlers
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app
