#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/.logs"

# Load nvm and use Node 22 (required by Vite 7)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
nvm use 22 > /dev/null 2>&1 || {
    echo "Error: Node 22 not found. Install with: nvm install 22"
    exit 1
}

mkdir -p "$PID_DIR" "$LOG_DIR"

# Parse args
WORKER_USER="${1:-}"
START_WORKER=0
if [[ -n "$WORKER_USER" ]]; then
    START_WORKER=1
fi

# Check if already running
if [[ -f "$PID_DIR/backend.pid" ]] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
    echo "Backend already running (PID $(cat "$PID_DIR/backend.pid"))"
    BACKEND_RUNNING=1
else
    BACKEND_RUNNING=0
fi

if [[ -f "$PID_DIR/frontend.pid" ]] && kill -0 "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null; then
    echo "Frontend already running (PID $(cat "$PID_DIR/frontend.pid"))"
    FRONTEND_RUNNING=1
else
    FRONTEND_RUNNING=0
fi

if [[ -f "$PID_DIR/worker.pid" ]] && kill -0 "$(cat "$PID_DIR/worker.pid")" 2>/dev/null; then
    echo "Worker already running (PID $(cat "$PID_DIR/worker.pid"))"
    WORKER_RUNNING=1
else
    WORKER_RUNNING=0
fi

# Start backend
if [[ "$BACKEND_RUNNING" -eq 0 ]]; then
    echo "Starting backend on http://localhost:8000 ..."
    cd "$PROJECT_DIR"
    python -m uvicorn kira.web.app:create_app --factory \
        --host 127.0.0.1 --port 8000 --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
    echo "  Backend started (PID $!), logs: .logs/backend.log"
fi

# Start frontend
if [[ "$FRONTEND_RUNNING" -eq 0 ]]; then
    echo "Starting frontend on http://localhost:5173 ..."
    cd "$PROJECT_DIR/frontend"
    npx vite --host 127.0.0.1 --port 5173 \
        > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    echo "  Frontend started (PID $!), logs: .logs/frontend.log"
fi

# Wait for backend to be ready
echo ""
echo "Waiting for backend..."
for i in $(seq 1 20); do
    if curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        echo "  Backend ready."
        break
    fi
    if [[ $i -eq 20 ]]; then
        echo "  Backend did not start in time. Check .logs/backend.log"
        exit 1
    fi
    sleep 0.5
done

# Wait for frontend to be ready
echo "Waiting for frontend..."
for i in $(seq 1 20); do
    if curl -sf http://127.0.0.1:5173 > /dev/null 2>&1; then
        echo "  Frontend ready."
        break
    fi
    if [[ $i -eq 20 ]]; then
        echo "  Frontend did not start in time. Check .logs/frontend.log"
        exit 1
    fi
    sleep 0.5
done

# Start worker if username provided
if [[ "$START_WORKER" -eq 1 && "$WORKER_RUNNING" -eq 0 ]]; then
    echo ""
    echo "Starting worker as '$WORKER_USER' ..."
    cd "$PROJECT_DIR"
    python -m kira worker --server http://localhost:8000 --user "$WORKER_USER" \
        > "$LOG_DIR/worker.log" 2>&1 &
    echo $! > "$PID_DIR/worker.pid"
    echo "  Worker started (PID $!), logs: .logs/worker.log"

    # Brief wait to check it connected
    sleep 2
    if kill -0 "$(cat "$PID_DIR/worker.pid")" 2>/dev/null; then
        echo "  Worker running."
    else
        echo "  Worker may have failed to start. Check .logs/worker.log"
    fi
fi

echo ""
echo "Kira Kanban Board is running:"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
if [[ "$START_WORKER" -eq 1 ]]; then
    echo "  Worker:   connected as '$WORKER_USER'"
fi
echo ""
echo "Logs:  .logs/backend.log, .logs/frontend.log, .logs/worker.log"
echo "Stop:  ./scripts/stop.sh"
echo ""
echo "Usage: ./scripts/start.sh [username]"
echo "  Pass a username to also start a worker (e.g. ./scripts/start.sh alice)"
