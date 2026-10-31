#!/usr/bin/env bash
# shellcheck disable=SC2154  # topology values are provided by the sourcing front-end

gen() { openssl rand -hex 16; }

db_url() { echo "postgresql+asyncpg://${PG_USER}:$2@$1:5432/$3"; }

render_secret() {
  local ns="$1" name="$2"; shift 2
  kubectl create secret generic "$name" --namespace "$ns" "$@" --dry-run=client -o yaml
}

build_secrets() {
  local rabbitmq_url="amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq.foc-messaging.svc.cluster.local:5672/"

  render_secret foc-messaging rabbitmq-secrets \
    --from-literal=RABBITMQ_DEFAULT_USER="$RABBITMQ_USER" \
    --from-literal=RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD" | sink foc-messaging rabbitmq-secrets

  render_secret foc-supplier supplier-secrets \
    --from-literal=POSTGRES_USER="$PG_USER" \
    --from-literal=POSTGRES_PASSWORD="$SUP_PW" \
    --from-literal=DATABASE_URL="$(db_url supplier-db "$SUP_PW" supplier_db)" | sink foc-supplier supplier-secrets

  render_secret foc-user user-secrets \
    --from-literal=POSTGRES_USER="$PG_USER" \
    --from-literal=POSTGRES_PASSWORD="$USER_PW" \
    --from-literal=DATABASE_URL="$(db_url user-db "$USER_PW" user_db)" \
    --from-literal=JWT_SECRET="$JWT_SECRET" \
    --from-literal=RABBITMQ_URL="$rabbitmq_url" | sink foc-user user-secrets

  render_secret foc-credit credit-secrets \
    --from-literal=POSTGRES_USER="$PG_USER" \
    --from-literal=POSTGRES_PASSWORD="$CREDIT_PW" \
    --from-literal=DATABASE_URL="$(db_url credit-db "$CREDIT_PW" credit_db)" \
    --from-literal=RABBITMQ_URL="$rabbitmq_url" | sink foc-credit credit-secrets

  render_secret foc-order order-secrets \
    --from-literal=POSTGRES_USER="$PG_USER" \
    --from-literal=POSTGRES_PASSWORD="$ORDER_PW" \
    --from-literal=DATABASE_URL="$(db_url order-db "$ORDER_PW" order_db)" | sink foc-order order-secrets

  render_secret foc-notification notification-secrets \
    --from-literal=POSTGRES_USER="$PG_USER" \
    --from-literal=POSTGRES_PASSWORD="$NOTIF_PW" \
    --from-literal=DATABASE_URL="$(db_url notification-db "$NOTIF_PW" notification_db)" | sink foc-notification notification-secrets

  render_secret foc-gateway gateway-secrets \
    --from-literal=JWT_SECRET="$JWT_SECRET" | sink foc-gateway gateway-secrets

  if [ "${INCLUDE_BACKUP:-0}" = "1" ]; then
    local ns
    for ns in foc-supplier foc-user foc-credit foc-order foc-notification; do
      render_secret "$ns" backup-s3 \
        --from-literal=AWS_ACCESS_KEY_ID="$BACKUP_AWS_ACCESS_KEY_ID" \
        --from-literal=AWS_SECRET_ACCESS_KEY="${BACKUP_AWS_SECRET_ACCESS_KEY:-}" | sink "$ns" backup-s3
    done
  fi
}
