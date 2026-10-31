#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=lib.sh
# shellcheck disable=SC1091  # dynamic path resolved at runtime
source "$SCRIPT_DIR/lib.sh"

CERT="${KUBESEAL_CERT:-$REPO_ROOT/infra/k8s/sealed/pub-cert.pem}"
SEALED_DIR="$REPO_ROOT/infra/k8s/sealed"
ENV_FILE="${SECRETS_ENV:-$SCRIPT_DIR/secrets.env}"

command -v kubeseal >/dev/null 2>&1 || { echo "kubeseal not found; install the sealed-secrets kubeseal CLI." >&2; exit 1; }
command -v yq >/dev/null 2>&1 || { echo "yq not found; install mikefarah yq v4." >&2; exit 1; }
case "$(yq --version 2>&1)" in *mikefarah*) ;; *) echo "yq must be mikefarah v4." >&2; exit 1 ;; esac
[ -f "$CERT" ] || { echo "cert '$CERT' missing. Run sealed-secrets-keygen.sh and place pub-cert.pem at infra/k8s/sealed/pub-cert.pem." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "env file '$ENV_FILE' missing. Copy secrets.env.example to secrets.env." >&2; exit 1; }

# shellcheck disable=SC1090  # path is user-provided at runtime
source "$ENV_FILE"

PG_USER="${PG_USER:-foc}"
RABBITMQ_USER="${RABBITMQ_USER:-foc}"

writeback() {
  local var="$1" val="$2" tmp
  if grep -qE "^${var}=" "$ENV_FILE"; then
    tmp="$(mktemp)"
    awk -v v="$var" -v val="$val" '$0 ~ "^"v"=" && !done { print v"="val; done=1; next } { print }' "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$var" "$val" >> "$ENV_FILE"
  fi
}

JWT_SECRET="${JWT_SECRET:-}";                   [ -n "$JWT_SECRET" ]   || { JWT_SECRET="$(gen)";       writeback JWT_SECRET "$JWT_SECRET"; }
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-}";     [ -n "$RABBITMQ_PASSWORD" ] || { RABBITMQ_PASSWORD="$(gen)"; writeback RABBITMQ_PASSWORD "$RABBITMQ_PASSWORD"; }
SUP_PW="${SUPPLIER_PG_PASSWORD:-}";             [ -n "$SUP_PW" ]       || { SUP_PW="$(gen)";    writeback SUPPLIER_PG_PASSWORD "$SUP_PW"; }
USER_PW="${USER_PG_PASSWORD:-}";                [ -n "$USER_PW" ]      || { USER_PW="$(gen)";   writeback USER_PG_PASSWORD "$USER_PW"; }
CREDIT_PW="${CREDIT_PG_PASSWORD:-}";            [ -n "$CREDIT_PW" ]    || { CREDIT_PW="$(gen)"; writeback CREDIT_PG_PASSWORD "$CREDIT_PW"; }
ORDER_PW="${ORDER_PG_PASSWORD:-}";              [ -n "$ORDER_PW" ]     || { ORDER_PW="$(gen)";  writeback ORDER_PG_PASSWORD "$ORDER_PW"; }
NOTIF_PW="${NOTIFICATION_PG_PASSWORD:-}";       [ -n "$NOTIF_PW" ]     || { NOTIF_PW="$(gen)";  writeback NOTIFICATION_PG_PASSWORD "$NOTIF_PW"; }

# shellcheck disable=SC2034  # consumed by build_secrets in lib.sh
INCLUDE_BACKUP=0
mkdir -p "$SEALED_DIR"

sink() {
  local out="$SEALED_DIR/$1-$2.yaml"
  kubeseal --cert "$CERT" --format yaml > "$out"
  yq -i '.metadata.annotations."argocd.argoproj.io/sync-options" = "Prune=false"' "$out"
}

build_secrets

echo "Sealed manifests written to $SEALED_DIR:"
for f in "$SEALED_DIR"/*.yaml; do echo "  $(basename "$f")"; done
echo
echo "Next: git add infra/k8s/sealed/*.yaml && commit. Keep '$ENV_FILE' private - never commit it."
