#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Building and starting Kira (Docker)..."
docker compose up -d --build

# Wait for backend to be healthy
echo ""
echo "Waiting for services..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "  Backend ready."
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "  Backend did not start in time."
        echo "  Check logs: docker compose logs backend"
        exit 1
    fi
    sleep 1
done

for i in $(seq 1 15); do
    if curl -sf http://localhost/ > /dev/null 2>&1; then
        echo "  Frontend ready."
        break
    fi
    if [[ $i -eq 15 ]]; then
        echo "  Frontend did not start in time."
        echo "  Check logs: docker compose logs frontend"
        exit 1
    fi
    sleep 1
done

echo ""
echo "Kira Kanban Board is running:"
echo "  App:      http://localhost"
echo "  API:      http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Logs:    docker compose logs -f"
echo "Stop:    ./scripts/docker-stop.sh"
echo ""

# Start worker interactively (prompts for credentials)
echo "Starting worker..."
echo ""
cd "$PROJECT_DIR"
exec kira worker --server http://localhost:8000
