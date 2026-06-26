#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${1:-docker-compose.yml}"
SERVICE_NAME="${SERVICE_NAME:-api}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
  echo "Docker Compose is not installed." >&2
  exit 1
fi

echo "Using compose file: $COMPOSE_FILE"
echo "Stopping and removing old containers..."
"${COMPOSE[@]}" down --remove-orphans

echo "Building latest image without cache..."
"${COMPOSE[@]}" build --no-cache --pull "$SERVICE_NAME"

echo "Starting new container..."
"${COMPOSE[@]}" up -d --force-recreate --no-deps "$SERVICE_NAME"

echo "Deployment finished. Current containers:"
"${COMPOSE[@]}" ps
