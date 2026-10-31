#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGETS=(shared api-gateway user-service supplier-service order-service credit-service notification-service)

failed=0
for t in "${TARGETS[@]}"; do
  cd "$ROOT/$t"
  if [ -x ".venv/bin/ruff" ]; then
    ruff=("./.venv/bin/ruff")
  else
    ruff=("ruff")
  fi
  echo "== ruff check $t =="
  "${ruff[@]}" check . || failed=1
  echo "== ruff format --check $t =="
  "${ruff[@]}" format --check . || failed=1
done

exit $failed
