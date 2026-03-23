.PHONY: setup up down clean logs restart migrate test lint dev-api dev-web shell-api shell-db

# === Setup ===
setup: ## Install all dependencies
	cd apps/api && poetry install
	cd apps/web && pnpm install

# === Docker ===
up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

clean: ## Stop and remove volumes
	docker compose down -v

logs: ## Tail all service logs
	docker compose logs -f

restart: ## Restart all services
	docker compose restart

# === Database ===
migrate: ## Run database migrations
	docker compose run --rm ekamcore-migrate

migration: ## Create a new migration (usage: make migration name=add_users)
	cd apps/api && poetry run alembic revision --autogenerate -m "$(name)"

# === Testing ===
test: test-api ## Run all tests

test-api: ## Run API tests
	cd apps/api && poetry run pytest -v --tb=short

test-web: ## Run web tests
	cd apps/web && pnpm test

test-integration: ## Run integration tests
	docker compose -f docker-compose.test.yml up -d
	cd apps/api && poetry run pytest tests/integration -v
	docker compose -f docker-compose.test.yml down

coverage: ## Run tests with coverage
	cd apps/api && poetry run pytest --cov=api --cov-report=html --cov-report=term

# === Linting ===
lint: ## Run all linters
	cd apps/api && poetry run ruff check .
	cd apps/web && pnpm lint

format: ## Format all code
	cd apps/api && poetry run ruff format .

# === Development ===
dev-api: ## Run API in dev mode
	cd apps/api && poetry run uvicorn api.main:app --reload --host 0.0.0.0 --port 8420

dev-web: ## Run web in dev mode
	cd apps/web && pnpm dev

# === Shell Access ===
shell-api: ## Shell into API container
	docker compose exec ekamcore-api /bin/bash

shell-db: ## Shell into PostgreSQL
	docker compose exec ekamcore-postgres psql -U ekamcore

# === Help ===
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
