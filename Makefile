# ─────────────────────────────────────────────────────────────
# FoC — Friend on Campus · Developer task runner
# Single entrypoint for common dev tasks. Run `make help`.
# ─────────────────────────────────────────────────────────────

# Backend Python services (each has its own venv + requirements.txt).
PY_SERVICES := api-gateway user-service supplier-service order-service credit-service notification-service

# Docker Compose command (v2).
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---- Environment --------------------------------------------
.PHONY: env
env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

# ---- Local (venv) developer workflow ------------------------
.PHONY: install
install: ## Create venvs + install deps (incl. shared) for every backend service
	@bash scripts/install.sh

.PHONY: test
test: ## Run pytest across all backend services
	@bash scripts/test-all.sh

.PHONY: lint
lint: ## ruff check across all backend services
	@bash scripts/lint-all.sh

.PHONY: fmt
fmt: ## ruff format across all backend services
	@for s in $(PY_SERVICES); do \
		echo "== ruff format $$s =="; \
		( cd $$s && ../$$s/.venv/bin/ruff format . 2>/dev/null || ruff format . ); \
	done

# Per-service test target, e.g. `make test-user-service`
.PHONY: $(addprefix test-,$(PY_SERVICES))
$(addprefix test-,$(PY_SERVICES)): test-%:
	@echo "== pytest $* =="
	@cd $* && ( .venv/bin/pytest 2>/dev/null || pytest )

# ---- Containerized workflow (Docker Compose) ----------------
.PHONY: build
build: env ## Build all images
	$(COMPOSE) build

.PHONY: up
up: env ## Build + start the whole stack (detached)
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

.PHONY: config
config: env ## Validate the compose file
	$(COMPOSE) config -q && echo "compose.yaml OK"

.PHONY: seed
seed: ## Run the supplier data seeder against the running stack
	$(COMPOSE) exec supplier-service python -c "import asyncio; from app.services.seeder import seed_suppliers; asyncio.run(seed_suppliers())"

.PHONY: clean
clean: ## Stop stack + remove volumes and local venvs
	$(COMPOSE) down -v
	@for s in $(PY_SERVICES); do rm -rf $$s/.venv; done
	@echo "Cleaned volumes and venvs"
