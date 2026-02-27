#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

if [[ -f "$PID_DIR/worker.pid" ]]; then
    PID=$(cat "$PID_DIR/worker.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping worker (PID $PID)..."
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
        echo "Worker stopped."
    else
        echo "Worker not running (stale PID $PID)."
    fi
    rm -f "$PID_DIR/worker.pid"
else
    echo "Worker not running (no PID file)."
fi
