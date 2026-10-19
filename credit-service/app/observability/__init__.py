# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Observability for credit-service (N2H: metrics, logs, readiness).

Modules:

- ``context``  correlation values (request id / order id / task id) used by logs
- ``metrics``  the Prometheus registry, every metric definition, query helpers
- ``middleware`` HTTP metrics + ``X-Request-Id`` propagation
- ``logging``  JSON log format for the ``app`` logger tree
- ``health``   broker connection state shared with ``GET /health/ready``
- ``summary``  assembles the JSON view served by ``GET /credits/observability/summary``

The service keeps ``GET /health`` untouched (``{"status": "ok"}``) because the
compose healthcheck and the root AGENTS.md contract depend on it.
"""
