# Deployment

## Local (mandatory — project M7)

The whole system runs locally via Docker Compose:

```bash
cp .env.example .env
make up      # build + start all services, DBs, and RabbitMQ
make ps      # verify health
make down
```

- Frontend: <http://localhost:5173>
- API Gateway: <http://localhost:8080>
- RabbitMQ management: <http://localhost:15672>

## TLS / transport security (backlog N1)

Backlog N1 requires encrypted transport. For local dev this is documented but
not enforced. For a hardened/cloud deployment, terminate TLS at the gateway
(or an ingress/reverse proxy in front of it) and reject plaintext.

## N2H: Cloud deployment & DevOps (project N4 / backlog NTH1)

Ideas to extend the mandatory containerized setup (team to scope):

- CI/CD pipeline (a starter workflow lives in `.github/workflows/ci.yml`).
- Push images to a registry on merge.
- Kubernetes manifests / Helm charts for cloud rollout + autoscaling.
- Infrastructure-as-code + a secrets manager.

> This file is a placeholder — expand as deployment decisions are made.
