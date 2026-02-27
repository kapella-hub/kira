#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

SERVER="${KIRA_SERVER_URL:-http://localhost:8000}"

# Check backend is reachable
if ! curl -sf "$SERVER/api/health" > /dev/null 2>&1; then
    echo "Warning: Server at $SERVER is not reachable."
    echo "Start it first: ./scripts/docker-start.sh"
    echo ""
fi

cd "$PROJECT_DIR"

# Run interactively -- will prompt for username and password as needed
exec kira worker --server "$SERVER"
