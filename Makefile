.DEFAULT_GOAL := help
API := apps/api
VENV := $(API)/.venv
PY := $(VENV)/bin/python

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Create the API virtualenv and install dependencies
	python3.12 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e "$(API)[dev]"

.PHONY: up
up: ## Start Postgres, Redis, and MinIO
	docker compose -f infra/docker-compose.yml up -d

.PHONY: down
down: ## Stop the local stack
	docker compose -f infra/docker-compose.yml down

.PHONY: clean-volumes
clean-volumes: ## Stop the local stack and delete its data
	docker compose -f infra/docker-compose.yml down -v

.PHONY: migrate
migrate: ## Apply Alembic migrations
	cd $(API) && .venv/bin/alembic upgrade head

.PHONY: revision
revision: ## Create a migration: make revision m="add asset table"
	cd $(API) && .venv/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: api
api: ## Run the API with reload
	cd $(API) && .venv/bin/uvicorn app.main:app --reload

.PHONY: worker
worker: ## Run the Celery worker
	cd $(API) && .venv/bin/celery -A app.worker.celery_app worker --loglevel=info

.PHONY: test
test: ## Run the API test suite
	cd $(API) && .venv/bin/pytest

.PHONY: lint
lint: ## Lint and typecheck the API
	cd $(API) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app tests

.PHONY: fix
fix: ## Autofix lint and formatting
	cd $(API) && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

.PHONY: check
check: lint test ## Everything CI runs for the API
