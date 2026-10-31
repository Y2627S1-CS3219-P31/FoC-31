#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
# shellcheck disable=SC1091  # dynamic path resolved at runtime
source "$SCRIPT_DIR/lib.sh"

PG_USER="${PG_USER:-foc}"
RABBITMQ_USER="${RABBITMQ_USER:-foc}"

existing() { kubectl get secret "$2" -n "$1" -o jsonpath="{.data.$3}" 2>/dev/null | base64 -d 2>/dev/null || true; }
require_ns() {
  kubectl get namespace "$1" >/dev/null 2>&1 || {
    echo "namespace '$1' missing. Run 'helm install/upgrade' first." >&2
    exit 1
  }
}
sink() { kubectl apply -f -; }

for ns in foc-supplier foc-user foc-credit foc-order foc-notification foc-messaging foc-gateway; do require_ns "$ns"; done

JWT_SECRET="${JWT_SECRET:-$(existing foc-user user-secrets JWT_SECRET)}"
JWT_SECRET="${JWT_SECRET:-$(existing foc-gateway gateway-secrets JWT_SECRET)}"
JWT_SECRET="${JWT_SECRET:-$(gen)}"

RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(existing foc-messaging rabbitmq-secrets RABBITMQ_DEFAULT_PASS)}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(gen)}"

SUP_PW="${SUPPLIER_PG_PASSWORD:-$(existing foc-supplier supplier-secrets POSTGRES_PASSWORD)}"; SUP_PW="${SUP_PW:-$(gen)}"
USER_PW="${USER_PG_PASSWORD:-$(existing foc-user user-secrets POSTGRES_PASSWORD)}"; USER_PW="${USER_PW:-$(gen)}"
CREDIT_PW="${CREDIT_PG_PASSWORD:-$(existing foc-credit credit-secrets POSTGRES_PASSWORD)}"; CREDIT_PW="${CREDIT_PW:-$(gen)}"
ORDER_PW="${ORDER_PG_PASSWORD:-$(existing foc-order order-secrets POSTGRES_PASSWORD)}"; ORDER_PW="${ORDER_PW:-$(gen)}"
NOTIF_PW="${NOTIFICATION_PG_PASSWORD:-$(existing foc-notification notification-secrets POSTGRES_PASSWORD)}"; NOTIF_PW="${NOTIF_PW:-$(gen)}"

# shellcheck disable=SC2034  # consumed by build_secrets in lib.sh
INCLUDE_BACKUP=0
if [ -n "${BACKUP_AWS_ACCESS_KEY_ID:-}" ]; then
  # shellcheck disable=SC2034  # consumed by build_secrets in lib.sh
  INCLUDE_BACKUP=1
fi

build_secrets

echo "Secrets applied."
