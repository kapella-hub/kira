#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Restarting Kira Kanban Board ==="
echo ""

"$SCRIPT_DIR/stop.sh"
echo ""
sleep 1
"$SCRIPT_DIR/start.sh"
