#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-nusisb_IsbUsersPS-986918902548}"
export AWS_REGION="${AWS_REGION:-ap-southeast-1}"

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
TF_DIR="$REPO_ROOT/infra/terraform"

IP="${1:-$(terraform -chdir="$TF_DIR" output -raw public_ip)}"
BUCKET="${2:-$(terraform -chdir="$TF_DIR" output -raw backup_bucket)}"

if ! command -v yq >/dev/null 2>&1; then
  echo "error: yq not found; install mikefarah yq (https://github.com/mikefarah/yq/)" >&2
  exit 1
fi
if ! yq --version 2>&1 | grep -q mikefarah; then
  echo "error: incompatible yq; the mikefarah yq is required, not the Python yq" >&2
  exit 1
fi

VALUES="$REPO_ROOT/infra/helm/foc/values-ec2.yaml"
ARGOCD_VALUES="$REPO_ROOT/infra/argocd/bootstrap/argocd-values.yaml"

IP="$IP" BUCKET="$BUCKET" yq -i '
  .["api-gateway"].ingress.host = strenv(IP) + ".nip.io" |
  .["frontend"].ingress.host = strenv(IP) + ".nip.io" |
  .["api-gateway"].env.CORS_ALLOWED_ORIGINS = "https://" + strenv(IP) + ".nip.io" |
  .["frontend"].env.API_BASE_URL = "https://" + strenv(IP) + ".nip.io" |
  .global.backup.bucket = strenv(BUCKET)
' "$VALUES"

IP="$IP" yq -i '
  .server.ingress.hostname = "argocd." + strenv(IP) + ".nip.io"
' "$ARGOCD_VALUES"

echo "IP:     $IP"
echo "Bucket: $BUCKET"
echo "Changed:"
echo "  $VALUES"
echo "  $ARGOCD_VALUES"
echo "Next: git add infra/helm/foc/values-ec2.yaml infra/argocd/bootstrap/argocd-values.yaml && git commit"
