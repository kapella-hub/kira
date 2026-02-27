#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Stopping worker (if running)..."
"$SCRIPT_DIR/stop-worker.sh" 2>/dev/null || true

echo "Stopping Docker containers..."
docker compose down

echo "Kira stopped."
