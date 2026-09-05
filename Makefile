# =============================================================================
# Marine Data Layer — operations Makefile
# Wraps the exact commands to bootstrap, run, migrate, seed, and validate the
# local stack. All commands use `docker compose` (compose.yaml) and .env.
# =============================================================================
SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help env build up down restart ps logs \
        migrate migrate-down seed-registry fixtures bootstrap \
        validate validate-compose validate-dockerfiles nuke

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing (never overwrites)
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example — edit local passwords before sharing."; else echo ".env already exists (left untouched)."; fi

build: ## Build all images
	$(COMPOSE) build

up: env ## Start the full stack in the background
	$(COMPOSE) up -d

down: ## Stop the stack (keep volumes)
	$(COMPOSE) down

restart: ## Restart the stack
	$(COMPOSE) down && $(COMPOSE) up -d

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Tail logs for all services (Ctrl-C to stop)
	$(COMPOSE) logs -f --tail=100

# ---------------------------------------------------------------------------
# Database migrations (Alembic runs inside the API image which has the deps)
# ---------------------------------------------------------------------------
migrate: ## Apply Alembic migrations (canonical schema)
	$(COMPOSE) run --rm --no-deps \
	  -v $(PWD)/alembic.ini:/app/alembic.ini:ro \
	  -v $(PWD)/migrations:/app/migrations:ro \
	  api alembic upgrade head

migrate-down: ## Roll back one migration
	$(COMPOSE) run --rm --no-deps \
	  -v $(PWD)/alembic.ini:/app/alembic.ini:ro \
	  -v $(PWD)/migrations:/app/migrations:ro \
	  api alembic downgrade -1
# ---------------------------------------------------------------------------
# Fixtures / seed data
# ---------------------------------------------------------------------------
seed-registry: ## Seed the dataset registry from fixtures (verified sources only)
	$(COMPOSE) run --rm --no-deps \
	  -v $(PWD)/fixtures:/app/fixtures:ro \
	  -v $(PWD)/scripts:/app/scripts:ro \
	  api python /app/scripts/seed_registry.py /app/fixtures/dataset_registry.seed.json

fixtures: seed-registry ## Load all local fixtures
	@echo "Fixtures loaded."

bootstrap: ## One-command bring-up: env -> build -> up -> wait -> migrate -> seed
	@$(MAKE) env
	@$(MAKE) build
	@$(MAKE) up
	@echo "Waiting for Postgres to become healthy..."
	@bash scripts/wait_for_healthy.sh postgres 120
	@$(MAKE) migrate
	@$(MAKE) seed-registry
	@echo "Bootstrap complete. API: http://localhost:$${API_PORT:-8000}  MCP: http://localhost:$${MCP_PORT:-9100}/mcp  Dashboard: http://localhost:$${DASHBOARD_PORT:-5173}  Grafana: http://localhost:$${GRAFANA_PORT:-3000}  Airflow: http://localhost:$${AIRFLOW_WEB_PORT:-8080}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
validate: validate-compose ## Run all local validations

validate-compose: ## Validate compose.yaml syntax/config
	$(COMPOSE) config >/dev/null && echo "compose.yaml: OK"

validate-dockerfiles: ## Lint Dockerfiles with hadolint if available
	@bash scripts/validate_dockerfiles.sh

nuke: ## Stop stack and DELETE all volumes (DESTRUCTIVE)
	$(COMPOSE) down -v

# ---------------------------------------------------------------------------
# Verification / testing
# ---------------------------------------------------------------------------
PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := $(PYTHON) -m pytest
RUFF := .venv/bin/ruff
NPM := cd dashboard && npx

.PHONY: test test-dash lint typecheck verify test-real integration e2e \
        data-health source-health

test: ## Run Python unit + fixture integration tests
	@echo "=== Python tests (unit + fixture integration) ==="
	$(PYTEST) tests/ -v --tb=short --timeout=30
	@echo ""
	@echo "=== RESULT: Python tests complete ==="

test-dash: ## Run dashboard TypeScript tests
	@echo "=== Dashboard tests ==="
	$(NPM) vitest run
	@echo ""
	@echo "=== RESULT: Dashboard tests complete ==="

lint: ## Lint Python source with ruff
	@echo "=== Ruff lint ==="
	$(RUFF) check src/ tests/
	@echo "=== RESULT: Lint clean ==="

typecheck: ## TypeScript type check for dashboard
	@echo "=== TypeScript typecheck ==="
	$(NPM) tsc -b --noEmit
	@echo "=== RESULT: Typecheck clean ==="

verify: ## Run ALL verification checks (test + dash + lint + typecheck)
	@echo "╔══════════════════════════════════════════╗"
	@echo "║  Marine Data Engine — Full Verification  ║"
	@echo "╚══════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) lint       2>&1 && echo "✓ Lint passed"       || echo "✗ Lint FAILED"
	@$(MAKE) typecheck  2>&1 && echo "✓ Typecheck passed"  || echo "✗ Typecheck FAILED"
	@$(MAKE) test       2>&1 && echo "✓ Python tests passed" || echo "✗ Python tests FAILED"
	@$(MAKE) test-dash  2>&1 && echo "✓ Dashboard tests passed" || echo "✗ Dashboard tests FAILED"
	@echo ""
	@echo "═══════════════════════════════════════════"
	@echo "  Verification complete. See above for any failures."
	@echo "  Real-source tests: 3 (run 'make test-real' when sources are available)"
	@echo "  E2E tests: 0 (run 'make e2e' with Docker stack running)"
	@echo "═══════════════════════════════════════════"

test-real: ## Run real-source integration tests (requires network + credentials)
	@echo "=== Real-source tests ==="
	@echo "3 real-source tests exist (tests/test_real_sources.py):"
	@echo "  - test_imd_cap_live_fetch      (IMD CAP RSS feed)"
	@echo "  - test_incois_erddap_catalog   (INCOIS ERDDAP catalog, >=16 dataset IDs)"
	@echo "  - test_mosdac_search           (MOSDAC search, 3RIMG_L2B_SST)"
	@echo ""
	@echo "They skip gracefully on network/TLS/parse/429 errors, and require"
	@echo "MDE_ENABLE_LIVE_SOURCES=true plus network access to exercise fully."
	@echo ""
	$(PYTEST) tests/ -m real_source -v --tb=short --timeout=60
	@echo "=== RESULT: Real-source tests complete ==="

integration: ## Run integration tests against Docker services
	@echo "=== Integration tests (requires 'make up' first) ==="
	@echo "WARNING: No Docker-backed integration tests exist yet."
	@echo "Prerequisite: docker compose up + migration + seed"
	@echo "When tests are added, run: pytest tests/ -m integration -v"
	@echo "=== RESULT: 0 integration tests available ==="

e2e: ## Run end-to-end tests (source → DB → API → dashboard)
	@echo "=== E2E tests (requires full stack) ==="
	@echo "WARNING: No e2e tests exist yet."
	@echo "When tests are added, run: pytest tests/ -m e2e -v"
	@echo "=== RESULT: 0 e2e tests available ==="

data-health: ## Query data-health from a running API
	@echo "=== Data health check ==="
	@curl -sS http://localhost:$${API_PORT:-8000}/v1/data-health | python3 -m json.tool || echo "FAILED: API not reachable at localhost:$${API_PORT:-8000}"

source-health: ## Test live source reachability
	@echo "=== Source reachability ==="
	@echo "IMD CAP RSS:" && curl -sS -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml || echo "UNREACHABLE"
	@echo "INCOIS ERDDAP:" && curl -sSk -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" "https://erddap.incois.gov.in/erddap/info/index.json?page=1&itemsPerPage=1" || echo "UNREACHABLE"
	@echo "MOSDAC search:" && curl -sS -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" "https://mosdac.gov.in/apios/datasets.json?count=1" || echo "UNREACHABLE"
	@echo "INCOIS PFZ page:" && curl -sS -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" "https://incois.gov.in/MarineFisheries/PfzAdvisory" || echo "UNREACHABLE"
