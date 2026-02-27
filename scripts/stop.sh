#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

STOPPED=0

stop_process() {
    local NAME="$1"
    local PID_FILE="$PID_DIR/${NAME}.pid"

    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping $NAME (PID $PID)..."
            kill "$PID" 2>/dev/null || true
            for i in $(seq 1 10); do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 0.3
            done
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null || true
            fi
            echo "  $NAME stopped."
            STOPPED=$((STOPPED + 1))
        else
            echo "$NAME not running (stale PID $PID)."
        fi
        rm -f "$PID_FILE"
    else
        echo "$NAME not running (no PID file)."
    fi
}

# Stop in reverse order: worker first, then frontend, then backend
stop_process "worker"
stop_process "frontend"
stop_process "backend"

# Clean up any orphaned processes on the ports
for PORT in 8000 5173; do
    ORPHAN=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [[ -n "$ORPHAN" ]]; then
        echo "Killing orphaned process on port $PORT (PID $ORPHAN)..."
        kill "$ORPHAN" 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
    fi
done

if [[ "$STOPPED" -gt 0 ]]; then
    echo ""
    echo "Kira Kanban Board stopped."
else
    echo ""
    echo "Nothing was running."
fi
