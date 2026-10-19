#!/usr/bin/env bash
# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
#
# Generate credit-service traffic so the observability stack has something to
# show. Every request goes through the real gateway path, so the numbers it
# produces are the numbers an operator would see in production.
#
# Usage:
#   FOC_TOKEN=<jwt> FOC_USER_ID=<user-uuid> scripts/load-credit.sh
#
# Optional environment variables:
#   BASE_URL     gateway base URL           (default http://localhost:8080)
#   REQUESTS     number of scenarios        (default 200)
#   CONCURRENCY  parallel workers           (default 8)
#   COURIER_ID   adds transfer traffic      (default: balance reads instead)
#
# Get the token from the login endpoint, e.g.
#   TOKEN=$(curl -s -X POST localhost:8080/api/users/login \
#     -H 'Content-Type: application/json' \
#     -d '{"email":"alice@u.nus.edu","password":"Passw0rd!"}' | jq -r .access_token)
#
# The mix is deliberate so the dashboard is not flat:
#   reserve + release      -> accepted / release ok
#   identical retry        -> 201 again, counted as duplicate_suppressed
#   same order, new amount -> 409 conflict
#   oversized reserve      -> 409 insufficient_credits
#   balance / history read -> 200 on read routes
#   transfer               -> transfer ok (only when COURIER_ID is set)
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
TOKEN="${FOC_TOKEN:-}"
USER_ID="${FOC_USER_ID:-}"
REQUESTS="${REQUESTS:-200}"
CONCURRENCY="${CONCURRENCY:-8}"
COURIER_ID="${COURIER_ID:-}"

if [[ -z "$TOKEN" || -z "$USER_ID" ]]; then
  cat >&2 <<'EOF'
error: FOC_TOKEN and FOC_USER_ID must be set.

  TOKEN=$(curl -s -X POST localhost:8080/api/users/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"alice@u.nus.edu","password":"Passw0rd!"}' | jq -r .access_token)
  UID_=$(curl -s localhost:8080/api/users/me -H "Authorization: Bearer $TOKEN" | jq -r .id)
  FOC_TOKEN=$TOKEN FOC_USER_ID=$UID_ scripts/load-credit.sh
EOF
  exit 1
fi

TALLY="$(mktemp)"
trap 'rm -f "$TALLY"' EXIT
RUN_ID="$$-$(date +%s)"
CODE="000"
BODY=""

# call METHOD PATH [BODY] -> prints "<body>\n<status code>"
call() {
  local method="$1" path="$2" body="${3:-}"
  local args=(
    -sS -X "$method" "$BASE_URL$path"
    -H "Authorization: Bearer $TOKEN"
    -H "Content-Type: application/json"
    -w $'\n%{http_code}'
  )
  if [[ -n "$body" ]]; then
    args+=(-d "$body")
  fi
  curl "${args[@]}" 2>/dev/null || printf '\n000'
}

split_response() {  # sets BODY and CODE from $1
  CODE="${1##*$'\n'}"
  BODY="${1%$'\n'*}"
}

record() { printf '%s\n' "$1" >>"$TALLY"; }

reserve_id() {  # order_id amount -> prints the reservation id (empty on failure)
  split_response "$(call POST /api/credits/reservations \
    "{\"user_id\":\"$USER_ID\",\"order_id\":\"$1\",\"amount\":$2}")"
  record "$CODE"
  printf '%s' "$BODY" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p'
}

scenario() {
  local i="$1"
  local order="load-$RUN_ID-$i"
  local rid=""
  case $((i % 10)) in
    0|1|2|3|4|5)
      rid="$(reserve_id "$order" $((i % 20 + 5)))"
      if [[ -n "$rid" ]]; then
        split_response "$(call POST "/api/credits/reservations/$rid/release")"
        record "$CODE"
      fi
      ;;
    6)
      # identical retry: returned as-is, counted as duplicate suppressed
      reserve_id "$order" 10 >/dev/null
      reserve_id "$order" 10 >/dev/null
      # same order, different amount: 409 conflict
      reserve_id "$order" 20 >/dev/null
      ;;
    7)
      reserve_id "load-oversize-$RUN_ID-$i" 99999 >/dev/null
      ;;
    8)
      if [[ -n "$COURIER_ID" ]]; then
        rid="$(reserve_id "$order" 15)"
        if [[ -n "$rid" ]]; then
          split_response "$(call POST "/api/credits/reservations/$rid/transfer" \
            "{\"courier_id\":\"$COURIER_ID\"}")"
          record "$CODE"
        fi
      else
        split_response "$(call GET "/api/credits/$USER_ID/balance")"
        record "$CODE"
      fi
      ;;
    9)
      split_response "$(call GET "/api/credits/$USER_ID/transactions?limit=10")"
      record "$CODE"
      ;;
  esac
}

echo "loading $BASE_URL: $REQUESTS scenarios, concurrency $CONCURRENCY"
for ((start = 1; start <= REQUESTS; start += CONCURRENCY)); do
  for ((offset = 0; offset < CONCURRENCY; offset++)); do
    idx=$((start + offset))
    if ((idx > REQUESTS)); then
      break
    fi
    scenario "$idx" &
  done
  wait || true
done

echo
echo "HTTP status codes:"
sort "$TALLY" | uniq -c | sort -rn | sed 's/^/  /'
cat <<'EOF'

Next:
  Grafana    http://localhost:3000   dashboard "Credit Service — Observability"
  JSON view  curl -s -H "Authorization: Bearer $FOC_TOKEN" \
               localhost:8080/api/credits/observability/summary | jq .
EOF
