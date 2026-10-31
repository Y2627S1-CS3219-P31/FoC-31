#!/usr/bin/env bash
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

KEY="${1:-}"
CRT="${2:-}"

usage() {
  echo "usage: $0 <path-to-tls.key> <path-to-tls.crt>" >&2
  echo "these come from scripts/sealed-secrets-keygen.sh, transferred to the node" >&2
  echo "out-of-band (e.g. SSM paste)." >&2
}

if [ -z "$KEY" ] || [ -z "$CRT" ] || [ ! -f "$KEY" ] || [ ! -f "$CRT" ]; then
  usage
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

if [ -n "$(kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key=active -o name)" ]; then
  echo "sealing key already present, skipping"
else
  kubectl create secret tls sealed-secrets-key --cert="$CRT" --key="$KEY" -n kube-system --dry-run=client -o yaml \
    | kubectl label --local -f - sealedsecrets.bitnami.com/sealed-secrets-key=active -o yaml \
    | kubectl apply -f -
fi

helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm upgrade --install argocd argo/argo-cd -n argocd --create-namespace \
  --version 10.11.6 -f "$REPO_ROOT/infra/argocd/bootstrap/argocd-values.yaml"

kubectl apply -f "$REPO_ROOT/infra/argocd/root.yaml"

deadline=$((SECONDS + 600))
apps="secrets foc"
while true; do
  all_ready=true
  for app in $apps; do
    status="$(kubectl get application "$app" -n argocd -o jsonpath='{.status.sync.status}|{.status.health.status}' 2>/dev/null || true)"
    if [ "$status" != "Synced|Healthy" ]; then
      all_ready=false
    fi
  done
  if [ "$all_ready" = true ]; then
    break
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "timed out waiting for applications to become Synced/Healthy:" >&2
    for app in $apps; do
      echo "  $app: $(kubectl get application "$app" -n argocd -o jsonpath='{.status.sync.status}|{.status.health.status}' 2>/dev/null || echo 'not found')" >&2
    done
    exit 1
  fi
  sleep 10
done

echo "admin password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo"
host="$(kubectl -n argocd get ingress argocd-server -o jsonpath='{.spec.rules[0].host}')"
echo "ArgoCD: https://$host"
