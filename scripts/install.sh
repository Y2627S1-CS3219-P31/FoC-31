#!/usr/bin/env bash
# Create a venv per backend service and install its deps + the shared library.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES=(api-gateway user-service supplier-service order-service credit-service notification-service)

for svc in "${SERVICES[@]}"; do
  echo "== installing $svc =="
  cd "$ROOT/$svc"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  # Install the shared contracts library (editable) then service deps.
  ./.venv/bin/pip install -e "$ROOT/shared"
  ./.venv/bin/pip install -r requirements.txt
  # ruff is used for lint/format across services.
  ./.venv/bin/pip install ruff >/dev/null
done

echo "All backend services installed."
echo "Frontend: run 'cd frontend && npm install' separately."
