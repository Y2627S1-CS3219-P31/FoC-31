#!/usr/bin/env bash
# Run ruff check for every backend service (+ the shared library).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGETS=(shared api-gateway user-service supplier-service order-service credit-service notification-service)

failed=0
for t in "${TARGETS[@]}"; do
  echo "== ruff check $t =="
  cd "$ROOT/$t"
  if [ -x ".venv/bin/ruff" ]; then
    ./.venv/bin/ruff check . || failed=1
  else
    ruff check . || failed=1
  fi
done

exit $failed
