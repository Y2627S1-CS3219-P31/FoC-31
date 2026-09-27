#!/usr/bin/env bash
# AI-influenced: authored with OpenCode (Claude Opus); see ai/usage-log.md.
#
# FoC Milestone D2 demo — User Service + Supplier Service through the API Gateway,
# no UI. This is the curl + jq twin of postman/FoC-D2.postman_collection.json;
# the numbered blocks below (01-07) match the Postman folders one-to-one.
#
# Deliberately NOT using `set -euo pipefail`: a failing demo step (e.g. an
# intentional 4xx) must not abort the whole walkthrough. Each block prints a
# header, shows the HTTP status + body, and pauses so you can narrate.
#
# Prerequisites (see postman/README.md):
#   - Stack up:      docker compose up --build -d   (wait for the gateway /health)
#   - OTP_DEV_MODE=true and BOOTSTRAP_ADMIN_* set in .env (the code is read from
#     `docker compose logs user-service`).
#   - Tools: curl, jq.
#
# Usage:
#   ./scripts/demo.sh                # interactive, pauses between steps
#   NO_PAUSE=1 ./scripts/demo.sh     # run straight through (CI-ish)

BASE_URL="${BASE_URL:-http://localhost:8080}"
ADMIN_EMAIL="${ADMIN_EMAIL:-e0000000@u.nus.edu}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin1234}"
CLIENT_EMAIL="${CLIENT_EMAIL:-demo$(date +%s)@u.nus.edu}"
CLIENT_PASSWORD="${CLIENT_PASSWORD:-Passw0rd1}"

# ---- helpers ---------------------------------------------------------------

pause() {
  if [ -z "${NO_PAUSE:-}" ]; then
    read -r -p "  --- press enter to continue ---"
  fi
}

header() {
  echo ""
  echo "============================================================"
  echo "  $1"
  echo "============================================================"
}

# req METHOD PATH [json-body] [bearer-token] [extra-header]
# Prints "HTTP <code>" then the pretty body. Returns the body on stdout via BODY.
BODY=""
CODE=""
req() {
  local method="$1" path="$2" body="${3:-}" token="${4:-}" extra="${5:-}"
  local args=(-sS -o /tmp/foc_demo_body -w '%{http_code}' -X "$method" "${BASE_URL}${path}")
  [ -n "$body" ] && args+=(-H "Content-Type: application/json" -d "$body")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer ${token}")
  [ -n "$extra" ] && args+=(-H "$extra")
  CODE="$(curl "${args[@]}")"
  BODY="$(cat /tmp/foc_demo_body)"
  echo "  ${method} ${path}  ->  HTTP ${CODE}"
  echo "$BODY" | jq . 2>/dev/null || echo "  $BODY"
}

jqget() { echo "$BODY" | jq -r "$1" 2>/dev/null; }

# ===========================================================================
header "00 Health — gateway is up"
req GET "/health"
pause

# ===========================================================================
header "01 Registration (User)"

echo "[01a] Register client -> expect 201"
req POST "/api/users/register" \
  "{\"email\":\"${CLIENT_EMAIL}\",\"password\":\"${CLIENT_PASSWORD}\",\"display_name\":\"Demo Client\",\"contact_number\":\"91234567\"}"
echo "  clientEmail=${CLIENT_EMAIL}"
pause

echo "[01b] Fetch OTP from user-service dev-mode log (OTP_DEV_MODE=true)"
OTP_CODE="${OTP_CODE:-}"
if [ -z "$OTP_CODE" ]; then
  # The log line looks like: "OTP_DEV_MODE active: verification code for <email> is <code> ..."
  OTP_CODE="$(docker compose logs user-service 2>/dev/null \
    | grep "verification code for ${CLIENT_EMAIL}" \
    | tail -n 1 \
    | grep -oE 'is [0-9]{6}' \
    | grep -oE '[0-9]{6}')"
fi
if [ -z "$OTP_CODE" ]; then
  echo "  Could not auto-read the OTP. Read it from 'docker compose logs user-service'"
  read -r -p "  and paste the 6-digit code here: " OTP_CODE
fi
echo "  OTP_CODE=${OTP_CODE}"
pause

echo "[01c] Verify OTP -> expect 200"
req POST "/api/users/otp/verify" \
  "{\"email\":\"${CLIENT_EMAIL}\",\"code\":\"${OTP_CODE}\"}"
pause

echo "[01d] Resend OTP -> expect 200 (generic)"
req POST "/api/users/otp/resend" "{\"email\":\"${CLIENT_EMAIL}\"}"
pause

echo "[01e] Register non-NUS email -> expect 422"
req POST "/api/users/register" \
  "{\"email\":\"someone@gmail.com\",\"password\":\"${CLIENT_PASSWORD}\",\"display_name\":\"Not NUS\"}"
pause

echo "[01f] Register duplicate verified email -> expect 409"
req POST "/api/users/register" \
  "{\"email\":\"${CLIENT_EMAIL}\",\"password\":\"${CLIENT_PASSWORD}\",\"display_name\":\"Dup\"}"
pause

# ===========================================================================
header "02 Authentication"

echo "[02a] Login admin -> expect 200, save adminToken"
req POST "/api/users/login" "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}"
ADMIN_TOKEN="$(jqget '.access_token')"
echo "  adminToken=${ADMIN_TOKEN:0:24}..."
pause

echo "[02b] Login client -> expect 200, save clientToken"
req POST "/api/users/login" "{\"email\":\"${CLIENT_EMAIL}\",\"password\":\"${CLIENT_PASSWORD}\"}"
CLIENT_TOKEN="$(jqget '.access_token')"
echo "  clientToken=${CLIENT_TOKEN:0:24}..."
pause

echo "[02c] Wrong password -> expect 401"
req POST "/api/users/login" "{\"email\":\"${CLIENT_EMAIL}\",\"password\":\"WrongPass9\"}"
pause

echo "[02d] GET /api/users/me as client -> expect 200, role==client, save clientUserId"
req GET "/api/users/me" "" "$CLIENT_TOKEN"
CLIENT_USER_ID="$(jqget '.id')"
echo "  clientUserId=${CLIENT_USER_ID}  role=$(jqget '.role')"
pause

echo "[02e] Resolve admin's own id (for later self-suspend/self-demote) via /me"
req GET "/api/users/me" "" "$ADMIN_TOKEN"
ADMIN_USER_ID="$(jqget '.id')"
echo "  adminUserId=${ADMIN_USER_ID}"
pause

echo "[02f] Protected route, no token -> expect 401 (gateway)"
req GET "/api/users/me"
pause

echo "[02g] Protected route, garbage token -> expect 401 (gateway)"
req GET "/api/users/me" "" "not.a.jwt"
pause

# ===========================================================================
header "03 RBAC evidence"

echo "[03a] Client POST /api/suppliers -> expect 403"
req POST "/api/suppliers" \
  "{\"name\":\"Nope\",\"category\":\"Food\",\"building\":\"COM1\"}" "$CLIENT_TOKEN"
pause

echo "[03b] Client POST /api/suppliers with spoofed X-User-Role: admin -> still 403 (gateway strips it)"
req POST "/api/suppliers" \
  "{\"name\":\"Spoof\",\"category\":\"Food\",\"building\":\"COM1\"}" "$CLIENT_TOKEN" "X-User-Role: admin"
pause

echo "[03c] Client GET /api/users/admin -> expect 403"
req GET "/api/users/admin" "" "$CLIENT_TOKEN"
pause

# ===========================================================================
header "04 Supplier queries (as client)"

echo "[04a] List page 1, page_size 5 -> expect 200"
req GET "/api/suppliers?page=1&page_size=5" "" "$CLIENT_TOKEN"
FIRST_SUPPLIER_ID="$(jqget '.items[0].id')"
echo "  firstSupplierId=${FIRST_SUPPLIER_ID}"
pause

echo "[04b] Filter by one category (Food) -> expect 200"
req GET "/api/suppliers?category=Food" "" "$CLIENT_TOKEN"
pause

echo "[04c] Filter by two categories (Food, Shopping) -> expect 200"
req GET "/api/suppliers?category=Food&category=Shopping" "" "$CLIENT_TOKEN"
pause

echo "[04d] Filter by zone (Central) -> expect 200"
req GET "/api/suppliers?zone=Central" "" "$CLIENT_TOKEN"
pause

echo "[04e] Keyword q=coffee -> expect 200"
req GET "/api/suppliers?q=coffee" "" "$CLIENT_TOKEN"
pause

echo "[04f] Combined filters -> expect 200"
req GET "/api/suppliers?category=Food&zone=Central&q=a&page=1&page_size=10" "" "$CLIENT_TOKEN"
pause

echo "[04g] Empty result query -> expect 200 with total 0 (not 404)"
req GET "/api/suppliers?q=zzzzznomatchzzzzz" "" "$CLIENT_TOKEN"
pause

echo "[04h] Get by id -> expect 200"
req GET "/api/suppliers/${FIRST_SUPPLIER_ID}" "" "$CLIENT_TOKEN"
pause

echo "[04i] Unknown id -> expect 404"
req GET "/api/suppliers/sup_doesnotexist" "" "$CLIENT_TOKEN"
pause

echo "[04j] Invalid page_size=1000 -> expect 422"
req GET "/api/suppliers?page_size=1000" "" "$CLIENT_TOKEN"
pause

# ===========================================================================
header "05 Supplier CRUD (as admin)"

CREATED_NAME="Demo Supplier $(date +%s)"
echo "[05a] Create -> expect 201, save supplierId"
req POST "/api/suppliers" \
  "{\"name\":\"${CREATED_NAME}\",\"category\":\"Printing\",\"building\":\"Demo Hall\",\"floor\":\"2\",\"startingTime\":\"09:00\",\"closingTime\":\"18:00\"}" \
  "$ADMIN_TOKEN"
SUPPLIER_ID="$(jqget '.id')"
echo "  supplierId=${SUPPLIER_ID}  name=${CREATED_NAME}"
pause

echo "[05b] Create invalid category -> expect 422"
req POST "/api/suppliers" \
  "{\"name\":\"Bad Cat\",\"category\":\"Groceries\",\"building\":\"Demo Hall\"}" "$ADMIN_TOKEN"
pause

echo "[05c] Create missing name -> expect 422"
req POST "/api/suppliers" \
  "{\"category\":\"Food\",\"building\":\"Demo Hall\"}" "$ADMIN_TOKEN"
pause

echo "[05d] Create bad time format -> expect 422"
req POST "/api/suppliers" \
  "{\"name\":\"Bad Time\",\"category\":\"Food\",\"building\":\"Demo Hall\",\"startingTime\":\"9am\"}" "$ADMIN_TOKEN"
pause

echo "[05e] PATCH one field (floor) -> expect 200, only floor changed"
req PATCH "/api/suppliers/${SUPPLIER_ID}" "{\"floor\":\"5\"}" "$ADMIN_TOKEN"
pause

echo "[05f] PATCH name: null -> expect 422"
req PATCH "/api/suppliers/${SUPPLIER_ID}" "{\"name\":null}" "$ADMIN_TOKEN"
pause

echo "[05g] Deactivate -> expect 200, active==false"
req POST "/api/suppliers/${SUPPLIER_ID}/deactivate" "" "$ADMIN_TOKEN"
pause

echo "[05h] Get deactivated by id -> expect 200, active==false"
req GET "/api/suppliers/${SUPPLIER_ID}" "" "$ADMIN_TOKEN"
pause

echo "[05i] List with q=<created name> as client -> expect total 0 (excluded from discovery)"
req GET "/api/suppliers?q=$(echo "$CREATED_NAME" | sed 's/ /%20/g')" "" "$CLIENT_TOKEN"
pause

echo "[05j] Deactivate again -> expect 409"
req POST "/api/suppliers/${SUPPLIER_ID}/deactivate" "" "$ADMIN_TOKEN"
pause

echo "[05k] Reactivate -> expect 200, active==true"
req POST "/api/suppliers/${SUPPLIER_ID}/reactivate" "" "$ADMIN_TOKEN"
pause

# ===========================================================================
header "06 Profile (as client)"

echo "[06a] PATCH /me display_name + contact_number -> expect 200"
req PATCH "/api/users/me" \
  "{\"display_name\":\"Demo Client Updated\",\"contact_number\":\"81234567\"}" "$CLIENT_TOKEN"
pause

echo "[06b] PATCH with role/is_suspended in body -> expect 422 (extra=forbid)"
req PATCH "/api/users/me" \
  "{\"display_name\":\"Sneaky\",\"role\":\"admin\",\"is_suspended\":false}" "$CLIENT_TOKEN"
pause

echo "[06c] PATCH invalid contact number -> expect 422"
req PATCH "/api/users/me" "{\"contact_number\":\"12345\"}" "$CLIENT_TOKEN"
pause

# ===========================================================================
header "07 User administration (as admin)"

echo "[07a] List users (limit/offset) -> expect 200"
req GET "/api/users/admin?limit=10&offset=0" "" "$ADMIN_TOKEN"
pause

echo "[07b] Suspend client -> expect 200"
req POST "/api/users/admin/${CLIENT_USER_ID}/suspend" "" "$ADMIN_TOKEN"
pause

echo "[07c] Client login while suspended -> expect 403"
req POST "/api/users/login" "{\"email\":\"${CLIENT_EMAIL}\",\"password\":\"${CLIENT_PASSWORD}\"}"
pause

echo "[07d] Admin suspend self -> expect 400"
req POST "/api/users/admin/${ADMIN_USER_ID}/suspend" "" "$ADMIN_TOKEN"
pause

echo "[07e] Unsuspend client -> expect 200"
req POST "/api/users/admin/${CLIENT_USER_ID}/unsuspend" "" "$ADMIN_TOKEN"
pause

NEW_ADMIN_EMAIL="admin$(date +%s)@u.nus.edu"
echo "[07f] Create another admin -> expect 201"
req POST "/api/users/admin" \
  "{\"email\":\"${NEW_ADMIN_EMAIL}\",\"password\":\"NewAdmin12345\",\"display_name\":\"Second Admin\"}" \
  "$ADMIN_TOKEN"
pause

echo "[07g] Promote client -> admin (role-change endpoint) -> expect 200"
req PATCH "/api/users/admin/${CLIENT_USER_ID}/role" "{\"role\":\"admin\"}" "$ADMIN_TOKEN"
pause

echo "[07h] Self-demotion rejected -> expect 400"
req PATCH "/api/users/admin/${ADMIN_USER_ID}/role" "{\"role\":\"client\"}" "$ADMIN_TOKEN"
pause

header "Demo complete"
echo "  clientEmail=${CLIENT_EMAIL}"
echo "  Use this verified email for newman mode (b):"
echo "    npx newman run postman/FoC-D2.postman_collection.json \\"
echo "      -e postman/FoC-local.postman_environment.json \\"
echo "      --folder '02 Authentication' --folder '03 RBAC evidence' \\"
echo "      --folder '04 Supplier queries (as client)' --folder '05 Supplier CRUD (as admin)' \\"
echo "      --folder '06 Profile (as client)' --folder '07 User administration (as admin)' \\"
echo "      --env-var clientEmail=${CLIENT_EMAIL}"
