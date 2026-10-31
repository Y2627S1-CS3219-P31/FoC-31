# ArgoCD GitOps runbook

This cluster is deployed with GitOps.
The `main` branch is the single source of truth, and ArgoCD continuously reconciles the single-node k3s cluster on EC2 to whatever is committed in git.
You deploy by merging to `main`; CI builds, scans, and commits image tags; ArgoCD syncs the cluster to the result.
This README is the operational runbook: architecture, the CI pipeline, first-time bootstrap, and day-2 operations.

## Architecture

### Delivery flow

```
git push / PR
    |
    v
CI  (lint -> test -> compose-e2e -> k3d-smoke -> image build + Trivy scan)
    |
    |  on merge to main
    v
GHCR (SHA-tagged images)  +  tag-bump commit to main (values-ec2.yaml, [skip ci])
    |
    v
ArgoCD  (watches main, auto-sync + self-heal)
    |
    v
k3s on EC2  (Traefik ingress, Let's Encrypt TLS)
```

### App-of-apps tree

A single root Application (`infra/argocd/root.yaml`) points at `infra/argocd/apps` and recurses.
Each child Application carries a sync-wave annotation so the platform comes up in dependency order before the workload.

```
root  (infra/argocd/apps, recurse)
 |
 +-- argocd          wave -3   argo-cd chart 10.11.6 (ArgoCD manages itself)
 +-- cert-manager    wave -2   cert-manager v1.21.3  (ServerSideApply=true)
 +-- sealed-secrets  wave -2   sealed-secrets chart 2.22.0 (kube-system)
 +-- namespaces      wave -1   infra/k8s/namespaces (static manifests)
 +-- platform        wave -1   infra/argocd/platform (ClusterIssuer)
 +-- secrets         wave -1   infra/k8s/sealed (committed SealedSecrets)
 +-- foc             wave  0   infra/helm/foc umbrella chart (values.yaml + values-ec2.yaml)
```

Lower (more negative) waves sync first, so ArgoCD, the controllers, the ClusterIssuer, the namespaces, and the secrets are all in place before the `foc` chart deploys.
On EC2 the chart's own namespace template is disabled (`createNamespaces: false` in `values-ec2.yaml`); the wave -1 `namespaces` app owns the namespaces instead.

## CI pipeline

A broken manifest merged to `main` is a broken deploy, so every manifest is validated before it can merge.
The pipeline (`.github/workflows/ci.yml`) is a gated DAG:

```
gate:
  Lint backend (shared + 6 services)   \
  Lint frontend                         |
  Static checks (helm/k8s/tf/shell/..)  |-- all must pass
  Trivy config (report-only)           /
      |
      v
  Backend tests (6 services)   Frontend Playwright   Compose E2E   k3d smoke
      |
      v
  Build + scan (8 images: 6 backend + frontend + pg-backup, Trivy, push on main)
      |
      v   (main only)
  Bump EC2 image tags  ->  commit "ci: deploy <sha> [skip ci]" to main
```

`Static checks` runs `helm template | kubeconform` for both value files, `kubeconform` over the namespaces, the argocd apps, and the sealed manifests, plus `terraform validate`, `actionlint`, and `shellcheck`, so bad manifests fail the gate rather than the cluster.
`Build + scan` gates on CRITICAL fixed vulnerabilities (via `.trivyignore`) and pushes to GHCR only on `main`.
`Bump EC2 image tags` is the only job that writes to the repo, and it runs only on `main`.

## First-time runbook

1. Provision the infrastructure:

   ```
   cd infra/terraform
   terraform init
   terraform apply
   ```

   This allocates the Elastic IP and the backups bucket.

2. Render the EC2 values from the Terraform outputs, then commit:

   ```
   scripts/render-ec2-values.sh
   git add infra/helm/foc/values-ec2.yaml infra/argocd/bootstrap/argocd-values.yaml
   git commit
   ```

   The script fills the `REPLACE_ME` placeholders (the `<eip>.nip.io` hosts) and the backup bucket name.

3. Make the GHCR packages public in the GitHub package settings.
   The repo is public, so this is the simplest route.
   Alternatively, add an `imagePullSecret` to the cluster and reference it from the chart, but public packages avoid managing a registry credential.

4. Generate the Sealed Secrets key:

   ```
   scripts/sealed-secrets-keygen.sh
   ```

   Store the generated key and the plaintext `infra/k8s/secrets/secrets.env` in the team password manager (both are gitignored and must never reach git), and copy the public cert to `infra/k8s/sealed/pub-cert.pem` (this one is committed; it only encrypts).

5. Produce and commit the SealedSecret manifests:

   ```
   infra/k8s/secrets/seal-secrets.sh
   git add infra/k8s/sealed/*.yaml
   git commit
   ```

   This reads `secrets.env`, builds each Secret, and seals it with `pub-cert.pem` into committed `<namespace>-<name>.yaml` manifests.

6. Fill the ClusterIssuer contact email in `infra/argocd/platform/cluster-issuer-letsencrypt-prod.yaml` (replace the `TODO-REPLACE-ME@example.com` placeholder), then commit.

7. Bootstrap the node.
   Open an SSM session to the node, transfer the sealing key and cert to it (paste over the SSM session, or use `aws ssm send-command` with a SecureString parameter, so the key never touches git), then load the key and apply the root Application:

   ```
   aws ssm start-session --target <instance-id>
   # transfer tls.key + tls.crt onto the node (SSM paste or SecureString param)
   scripts/argocd-bootstrap.sh <tls.key> <tls.crt>
   ```

   The bootstrap script loads the key into `kube-system` before the sealed-secrets controller installs, so the controller adopts the team-held key, then installs ArgoCD and applies the root app so the app-of-apps tree syncs itself.

## Day-2 operations

- Deploy: merge to `main`.
  CI builds, scans, and bumps the image tags, and ArgoCD syncs the new commit.

- Roll back: `git revert` the `ci: deploy <sha>` tag-bump commit.
  ArgoCD syncs the cluster back to the previous images.

- Pause auto-sync: disable the Application's automated `syncPolicy`, or run `argocd app set <app> --sync-policy none`.
  Re-enable by restoring the `syncPolicy`.

- Add or rotate a secret: edit `infra/k8s/secrets/secrets.env`, re-run `infra/k8s/secrets/seal-secrets.sh`, and commit the updated sealed manifest.
  Then `kubectl rollout restart` the affected deployment, because env-var secrets do not hot-reload.

- Restore the sealing key on a rebuilt cluster: re-run the bootstrap key-load step with the backed-up key before the sealed-secrets controller installs, so it adopts the existing key and the committed SealedSecrets still decrypt.

- SSM port-forward fallback (when the UI ingress is unavailable):

  ```
  aws ssm start-session --target <instance-id> \
    --document-name AWS-StartPortForwardingSession \
    --parameters '{"portNumber":["<nodeport>"],"localPortNumber":["<local>"]}'
  kubectl -n argocd port-forward svc/argocd-server 8080:80
  # initial admin password:
  kubectl -n argocd get secret argocd-initial-admin-secret \
    -o jsonpath='{.data.password}' | base64 -d; echo
  ```

## Turn the ArgoCD ingress off

Set `server.ingress.enabled: false` in `infra/argocd/bootstrap/argocd-values.yaml` and commit.
Reach the UI with the SSM port-forward fallback above.

## ServerSideApply note

`ServerSideApply=true` is set only on the cert-manager Application.
Its CRDs are too large for the client-side-apply `last-applied-configuration` annotation (a known cert-manager + ArgoCD issue), and server-side apply avoids that limit.
The `foc` chart does not need it, so it is not enabled there.

## Autostop note

The ArgoCD controller, repo-server, and redis add a baseline CPU draw even when nothing is deploying.
After the cluster has been running, measure the real idle CPU and re-tune the `idle_cpu_threshold_percent` Terraform variable (default 5) accordingly.
If the threshold is left too low, the autostop may read ArgoCD's baseline as "busy", or too high and it may stop the node under you.

## Required status checks

Branch protection on `main` is a manual GitHub setting (Settings -> Branches -> branch protection rule).
Mark the gate jobs as required so a red CI run cannot merge:

- `Lint backend (shared)`, `Lint backend (api-gateway)`, `Lint backend (user-service)`, `Lint backend (supplier-service)`, `Lint backend (order-service)`, `Lint backend (credit-service)`, `Lint backend (notification-service)`
- `Lint frontend`
- `Static checks (helm/k8s/terraform/shell/actions)`
- `Backend tests (api-gateway)`, `Backend tests (user-service)`, `Backend tests (supplier-service)`, `Backend tests (order-service)`, `Backend tests (credit-service)`, `Backend tests (notification-service)`
- `Frontend Playwright`
- `Compose E2E`
- `k3d smoke`
- `Build + scan (api-gateway)`, `Build + scan (user-service)`, `Build + scan (supplier-service)`, `Build + scan (order-service)`, `Build + scan (credit-service)`, `Build + scan (notification-service)`, `Build + scan (frontend)`, `Build + scan (pg-backup)`

The GHCR push step and the `Bump EC2 image tags` job are not gate checks; they run only on `main` after the gates pass.
`Trivy config (report-only)` uploads a SARIF report and does not gate.

## Open item

The `ORDER_PHOTO_BUCKET` / `ORDER_PHOTO_REGION` env vars and the S3 permissions raised in the PR #14 review are not handled here and remain open.
They need a dedicated bucket, the matching IAM permission on the instance role, and the env wired through the chart before order photo upload works on EC2.
