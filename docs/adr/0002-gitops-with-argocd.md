# ADR 0002: GitOps deployment with ArgoCD

- Status: accepted
- Date: 2026-10-31

## Context

The system runs on a single-node k3s cluster on an EC2 box.
We needed a repeatable way to deploy it, keep the cluster in sync with the repository, and make deployments auditable for grading.
The node has no public Kubernetes API (the security group allows only 80/443) and is reached through AWS SSM, so the deploy mechanism cannot depend on an operator running `kubectl apply` from a laptop against the API server.
This ADR records the deployment decisions the team made for this setup; it documents those choices, it does not make them.

## Decision

- The node gets a stable address from a Terraform-allocated Elastic IP, and hosts are derived from it as `<eip>.nip.io` for the app and `argocd.<eip>.nip.io` for the ArgoCD UI, so the public DNS name survives instance stop/start.
- CI builds and scans the images, pushes SHA-tagged images to GHCR, and commits those tags to `main`; ArgoCD then deploys whatever is in git, so `main` is the single deploy surface and every deploy is a commit.
- The ArgoCD UI is exposed through the Traefik ingress with a Let's Encrypt certificate, with `aws ssm start-session` port-forwarding kept as an always-available fallback.
- Secrets use Bitnami Sealed Secrets with a team-held, pre-generated key; key renewal is turned off so the same key keeps decrypting the committed SealedSecrets.
- The topology is app-of-apps: a root Application points at `infra/argocd/apps`, and ArgoCD manages itself, cert-manager, the sealed-secrets controller, the platform ClusterIssuer, the namespaces, the sealed secrets, and the `foc` umbrella chart, ordered by sync waves.

## Consequences

- The cluster state is fully described in git and reconciled automatically, so deployments are reproducible and auditable, and a roll back is a `git revert`.
- The cluster is a single node with no high availability; losing the node means rebuilding it from Terraform and git.
- Losing the Sealed Secrets key means every committed SealedSecret must be re-sealed with a new key, because the old ciphertext can no longer be decrypted.
- Because `main` is the deploy surface, a broken manifest merged to `main` is a broken deploy, so manifests are validated in CI before merge.
- The ArgoCD applicationSet controller runs at 0 replicas to save baseline resources on the single node, since app-of-apps does not need it.
