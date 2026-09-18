#!/usr/bin/env bash
# Run pytest for every backend service. Uses the service venv if present,
# otherwise falls back to the ambient `pytest`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES=(api-gateway user-service supplier-service order-service credit-service notification-service)

failed=0
for svc in "${SERVICES[@]}"; do
  echo "== pytest $svc =="
  cd "$ROOT/$svc"
  if [ -x ".venv/bin/pytest" ]; then
    ./.venv/bin/pytest || failed=1
  else
    pytest || failed=1
  fi
done

exit $failed
