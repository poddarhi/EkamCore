.PHONY: setup up down clean logs restart migrate test lint dev-api dev-web shell-api shell-db \
        ollama-start ollama-stop ollama-status paperless-logs paperless-token paperless-shell

# === Setup ===
setup: ## Install all dependencies
	cd apps/api && poetry install
	cd apps/web && pnpm install

# === Ollama (runs natively, not in Docker) ===
ollama-start: ## Start Ollama natively on host
	@if ! pgrep -x ollama > /dev/null; then \
		echo "Starting Ollama..."; \
		ollama serve & \
		sleep 2; \
		echo "Ollama started"; \
	else \
		echo "Ollama already running"; \
	fi

ollama-stop: ## Stop Ollama
	@pkill ollama 2>/dev/null || echo "Ollama not running"

ollama-status: ## Show loaded Ollama models
	@ollama list 2>/dev/null || echo "Ollama not running"

# === PaperlessNGX ===
paperless-logs: ## Tail PaperlessNGX logs
	docker compose logs -f ekamcore-paperless

paperless-token: ## Create Paperless API token for admin
	@docker compose exec ekamcore-paperless python3 manage.py create_api_token admin

paperless-shell: ## Shell into PaperlessNGX container
	docker compose exec ekamcore-paperless bash

# === Docker ===
up: ollama-start ## Start all services (also ensures Ollama is running)
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 5
	@docker compose ps
	@echo ""
	@echo "Stack is up. Access:"
	@echo "  Web:        https://localhost"
	@echo "  API:        https://localhost/api/v1"
	@echo "  Health:     https://localhost/health"
	@echo "  Paperless:  https://localhost/paperless/"
	@echo "  (Paperless login: admin / check .env for password)"

down: ## Stop all containers (Ollama keeps running — use 'make ollama-stop' to stop)
	docker compose down
	@echo "Containers stopped. Ollama still running (use 'make ollama-stop' to stop)"

clean: ## Stop and remove all containers and volumes (DELETES ALL DATA)
	docker compose down -v
	@echo "All containers and volumes removed"
	@echo "WARNING: All data has been deleted"

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
