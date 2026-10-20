#!/usr/bin/env bash
# AI-influenced: concurrent-accept race demo authored with Claude Code (Claude Opus 4.8); see ai/usage-log.md.
#
# Demonstrates D3 Part 1.4 (concurrent accept): two couriers race to accept the
# same open order through the API Gateway; exactly one wins (200) and the other
# loses (409). Exits 0 only on that outcome.
#
# Overridable: GATEWAY (default http://localhost:8080), MAILPIT (default http://localhost:8025).

set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8080}"
MAILPIT="${MAILPIT:-http://localhost:8025}"
PASSWORD="Passw0rd1"

for bin in curl jq python3; do
  command -v "$bin" >/dev/null 2>&1 || { echo "missing required tool: $bin" >&2; exit 1; }
done

log() { echo "[d3-race] $*" >&2; }

# register_user <label> -> echoes "<access_token> <user_id>" on stdout
register_user() {
  local label="$1"
  local email="d3race$(date +%s)_${RANDOM}@u.nus.edu"
  log "registering $label ($email)"
  curl -s -o /dev/null -X POST "$GATEWAY/api/users/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\",\"display_name\":\"D3 Race $label\",\"contact_number\":\"91234567\"}"

  local code="" i
  for i in $(seq 1 20); do
    code="$(curl -s "$MAILPIT/api/v1/search?query=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote('to:\"'+sys.argv[1]+'\"'))" "$email")" \
      | jq -r '.messages[0].Snippet // ""' | grep -oE '[0-9]{6}' | head -1 || true)"
    [ -n "$code" ] && break
    sleep 1
  done
  [ -n "$code" ] || { log "no OTP for $email"; exit 1; }

  curl -s -o /dev/null -X POST "$GATEWAY/api/users/otp/verify" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"code\":\"$code\"}"

  local login token uid
  login="$(curl -s -X POST "$GATEWAY/api/users/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\"}")"
  token="$(echo "$login" | jq -r '.access_token')"
  [ -n "$token" ] && [ "$token" != "null" ] || { log "login failed for $email"; exit 1; }
  uid="$(curl -s "$GATEWAY/api/users/me" -H "Authorization: Bearer $token" | jq -r '.id')"
  echo "$token $uid"
}

read -r REQ_TOKEN REQ_ID < <(register_user requester)
read -r C1_TOKEN C1_ID < <(register_user courier1)
read -r C2_TOKEN C2_ID < <(register_user courier2)
log "requester=$REQ_ID courier1=$C1_ID courier2=$C2_ID"

SUPPLIER_ID="$(curl -s "$GATEWAY/api/suppliers?page_size=50" -H "Authorization: Bearer $REQ_TOKEN" \
  | jq -r '[.items[] | select(.active == true)][0].id')"
[ -n "$SUPPLIER_ID" ] && [ "$SUPPLIER_ID" != "null" ] || { log "no active supplier"; exit 1; }
log "supplier=$SUPPLIER_ID"

DEADLINE="$(python3 -c 'import datetime;print((datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat())')"
ORDER_ID="$(curl -s -X POST "$GATEWAY/api/orders" \
  -H "Authorization: Bearer $REQ_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"name\":\"D3 Race Order\",\"details\":\"race demo\",\"reward\":10,\"deadline\":\"$DEADLINE\",\"supplier_id\":\"$SUPPLIER_ID\",\"pickup_location\":\"COM1\",\"delivery_location\":\"COM2\"}" \
  | jq -r '.order_id')"
[ -n "$ORDER_ID" ] && [ "$ORDER_ID" != "null" ] || { log "order creation failed"; exit 1; }
log "order=$ORDER_ID — firing both couriers concurrently"

S1_FILE="$(mktemp)"; S2_FILE="$(mktemp)"
trap 'rm -f "$S1_FILE" "$S2_FILE"' EXIT

curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY/api/orders/$ORDER_ID/accept" \
  -H "Authorization: Bearer $C1_TOKEN" > "$S1_FILE" &
curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY/api/orders/$ORDER_ID/accept" \
  -H "Authorization: Bearer $C2_TOKEN" > "$S2_FILE" &
wait

S1="$(cat "$S1_FILE")"; S2="$(cat "$S2_FILE")"
echo "courier1 accept -> HTTP $S1"
echo "courier2 accept -> HTTP $S2"

if { [ "$S1" = "200" ] && [ "$S2" = "409" ]; } || { [ "$S1" = "409" ] && [ "$S2" = "200" ]; }; then
  echo "PASS: exactly one courier won (one 200, one 409)"
  exit 0
fi
echo "FAIL: expected one 200 and one 409, got $S1 and $S2" >&2
exit 1
