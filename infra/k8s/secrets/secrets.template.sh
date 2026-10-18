#!/usr/bin/env bash
set -euo pipefail

# Creates the per-namespace Kubernetes Secrets for Campus Errand. Never commit
# real values; override via environment variables (see secrets.env.example).
# Run AFTER `helm install/upgrade` has created the namespaces.
# Idempotent: reuses a password already in the cluster (or an env-supplied one)
# so re-running never breaks a live database or the shared JWT/broker creds.

PG_USER="${PG_USER:-foc}"
RABBITMQ_USER="${RABBITMQ_USER:-foc}"

existing() { kubectl get secret "$2" -n "$1" -o jsonpath="{.data.$3}" 2>/dev/null | base64 -d 2>/dev/null || true; }
gen() { openssl rand -hex 16; }
require_ns() {
  kubectl get namespace "$1" >/dev/null 2>&1 || {
    echo "namespace '$1' missing. Run 'helm install/upgrade' first." >&2
    exit 1
  }
}
apply_secret() {
  local ns="$1" name="$2"; shift 2
  kubectl create secret generic "$name" --namespace "$ns" "$@" \
    --dry-run=client -o yaml | kubectl apply -f -
}
db_url() { echo "postgresql+asyncpg://${PG_USER}:$2@$1:5432/$3"; }

for ns in foc-supplier foc-user foc-credit foc-order foc-notification foc-messaging foc-gateway; do require_ns "$ns"; done

# Shared across namespaces, so they must resolve to one value on every run.
JWT_SECRET="${JWT_SECRET:-$(existing foc-user user-secrets JWT_SECRET)}"
JWT_SECRET="${JWT_SECRET:-$(existing foc-gateway gateway-secrets JWT_SECRET)}"
JWT_SECRET="${JWT_SECRET:-$(gen)}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(existing foc-messaging rabbitmq-secrets RABBITMQ_DEFAULT_PASS)}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(gen)}"
RABBITMQ_URL="amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq.foc-messaging.svc.cluster.local:5672/"

apply_secret foc-messaging rabbitmq-secrets \
  --from-literal=RABBITMQ_DEFAULT_USER="$RABBITMQ_USER" \
  --from-literal=RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD"

SUP_PW="$(existing foc-supplier supplier-secrets POSTGRES_PASSWORD)"; SUP_PW="${SUP_PW:-$(gen)}"
apply_secret foc-supplier supplier-secrets \
  --from-literal=POSTGRES_USER="$PG_USER" \
  --from-literal=POSTGRES_PASSWORD="$SUP_PW" \
  --from-literal=DATABASE_URL="$(db_url supplier-db "$SUP_PW" supplier_db)"

USER_PW="$(existing foc-user user-secrets POSTGRES_PASSWORD)"; USER_PW="${USER_PW:-$(gen)}"
apply_secret foc-user user-secrets \
  --from-literal=POSTGRES_USER="$PG_USER" \
  --from-literal=POSTGRES_PASSWORD="$USER_PW" \
  --from-literal=DATABASE_URL="$(db_url user-db "$USER_PW" user_db)" \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=RABBITMQ_URL="$RABBITMQ_URL"

CREDIT_PW="$(existing foc-credit credit-secrets POSTGRES_PASSWORD)"; CREDIT_PW="${CREDIT_PW:-$(gen)}"
apply_secret foc-credit credit-secrets \
  --from-literal=POSTGRES_USER="$PG_USER" \
  --from-literal=POSTGRES_PASSWORD="$CREDIT_PW" \
  --from-literal=DATABASE_URL="$(db_url credit-db "$CREDIT_PW" credit_db)" \
  --from-literal=RABBITMQ_URL="$RABBITMQ_URL"

ORDER_PW="$(existing foc-order order-secrets POSTGRES_PASSWORD)"; ORDER_PW="${ORDER_PW:-$(gen)}"
apply_secret foc-order order-secrets \
  --from-literal=POSTGRES_USER="$PG_USER" \
  --from-literal=POSTGRES_PASSWORD="$ORDER_PW" \
  --from-literal=DATABASE_URL="$(db_url order-db "$ORDER_PW" order_db)"

NOTIF_PW="$(existing foc-notification notification-secrets POSTGRES_PASSWORD)"; NOTIF_PW="${NOTIF_PW:-$(gen)}"
apply_secret foc-notification notification-secrets \
  --from-literal=POSTGRES_USER="$PG_USER" \
  --from-literal=POSTGRES_PASSWORD="$NOTIF_PW" \
  --from-literal=DATABASE_URL="$(db_url notification-db "$NOTIF_PW" notification_db)"

# foc-gateway shares the JWT secret with user-service (gateway validates, user issues).
apply_secret foc-gateway gateway-secrets \
  --from-literal=JWT_SECRET="$JWT_SECRET"

# Backup S3 credentials (per DB namespace), only when a bucket is configured.
# For AWS leave S3_ENDPOINT_URL unset; for a local MinIO test set the endpoint
# in the chart and point these at MinIO.
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  for ns in foc-supplier foc-user foc-credit foc-order foc-notification; do
    apply_secret "$ns" backup-s3 \
      --from-literal=S3_BUCKET="$BACKUP_S3_BUCKET" \
      --from-literal=AWS_ACCESS_KEY_ID="${BACKUP_AWS_ACCESS_KEY_ID:-}" \
      --from-literal=AWS_SECRET_ACCESS_KEY="${BACKUP_AWS_SECRET_ACCESS_KEY:-}"
  done
fi

echo "Secrets applied."
