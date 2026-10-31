#!/usr/bin/env bash
set -euo pipefail

DIR="${1:-$HOME/foc-sealed-secrets-key}"
echo "Output directory: $DIR"

if [[ -e "$DIR/tls.key" || -e "$DIR/tls.crt" ]]; then
  echo "ERROR: $DIR/tls.key or $DIR/tls.crt already exists. Refusing to overwrite." >&2
  exit 1
fi

mkdir -p "$DIR"
chmod 700 "$DIR"

openssl req -x509 -nodes -newkey rsa:4096 \
  -keyout "$DIR/tls.key" \
  -out "$DIR/tls.crt" \
  -subj "/CN=sealed-secret/O=sealed-secret" \
  -days 3650

chmod 600 "$DIR/tls.key"

echo ""
echo "Key pair generated in $DIR"
echo ""
echo "NEXT STEPS:"
echo "  1. Store tls.key and tls.crt in the team password manager."
echo "     This is the ONLY backup — losing the key makes every committed SealedSecret undecryptable."
echo "  2. Copy the public cert to the repo (committed; used by seal-secrets.sh):"
echo "       cp \"$DIR/tls.crt\" infra/k8s/sealed/pub-cert.pem"
echo "  3. NEVER commit tls.key — the private key must stay out of the repository."
echo "  4. During bootstrap, load the pair into kube-system BEFORE ArgoCD installs the controller"
echo "     so the controller adopts this key."
