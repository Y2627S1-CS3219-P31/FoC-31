#!/usr/bin/env bash
# Minimal host:port readiness wait. Useful in container entrypoints / CI to
# block until a dependency (Postgres, RabbitMQ) accepts connections.
#
# Usage: wait-for-it.sh host:port [timeout_seconds]
set -euo pipefail

hostport="${1:?usage: wait-for-it.sh host:port [timeout]}"
host="${hostport%%:*}"
port="${hostport##*:}"
timeout="${2:-30}"

echo "Waiting for $host:$port (timeout ${timeout}s)..."
for _ in $(seq "$timeout"); do
  if (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1; then
    echo "$host:$port is available."
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for $host:$port" >&2
exit 1
