#!/usr/bin/env bash
set -euo pipefail

# Drives load at /api/suppliers to exercise the HPA on the stateless tier.
# Provisions a throwaway JWT through the gateway, then runs k6.
# Overrides: BASE_URL (skip port-forward), TOKEN (skip provisioning),
# PORT, EMAIL_DOMAIN.

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-18080}"
DOMAIN="${EMAIL_DOMAIN:-u.nus.edu}"
PF=""

if [ -z "${BASE_URL:-}" ]; then
  kubectl port-forward -n foc-gateway svc/api-gateway "$PORT:8000" >/tmp/foc-loadtest-pf.log 2>&1 &
  PF=$!; trap '[ -n "$PF" ] && kill "$PF" 2>/dev/null || true' EXIT
  BASE_URL="http://localhost:$PORT"
  sleep 4
fi

if [ -z "${TOKEN:-}" ]; then
  EMAIL="load$(date +%s)@$DOMAIN"; PW="Passw0rd123"
  curl -s -X POST "$BASE_URL/api/users/register" -H 'content-type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\",\"display_name\":\"Load\"}" >/dev/null
  sleep 2
  CODE=$(kubectl logs deployment/user-service -n foc-user 2>/dev/null \
    | grep -oE "verification code for $EMAIL is [0-9]+" | tail -1 | grep -oE "[0-9]+$")
  curl -s -X POST "$BASE_URL/api/users/otp/verify" -H 'content-type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"code\":\"$CODE\"}" >/dev/null
  TOKEN=$(curl -s -X POST "$BASE_URL/api/users/login" -H 'content-type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
fi

echo "HPA before:"; kubectl get hpa -A
BASE_URL="$BASE_URL" TOKEN="$TOKEN" k6 run "$HERE/load-test.js"
echo "HPA after:"; kubectl get hpa -A
