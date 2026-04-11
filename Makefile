.PHONY: setup up down clean logs restart migrate migration seed \
       test test-api test-web test-mobile test-integration coverage \
       lint format benchmark \
       shell-api shell-db shell-redis \
       ollama-start ollama-stop ollama-status \
       paperless-logs paperless-token paperless-shell \
       backup restore backup-list \
       dev-api dev-web help

# === Setup ===
setup: ## Install all dependencies and create .env
	cd apps/api && poetry install
	cd apps/web && pnpm install
	cd apps/mobile && npm install 2>/dev/null || true
	cp -n .env.example .env 2>/dev/null || true
	@echo "Setup complete. Run 'make up' to start the stack."

# === Docker Stack ===
up: ollama-start ## Start all services (ensures Ollama is running)
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 10
	@docker compose ps
	@echo ""
	@echo "EkamCore is running:"
	@echo "  Web:        https://localhost"
	@echo "  API:        https://localhost/api/v1"
	@echo "  Health:     https://localhost/health"
	@echo "  Paperless:  https://localhost/paperless/"

down: ## Stop all containers (Ollama keeps running)
	docker compose down
	@echo "Containers stopped. Ollama still running (use 'make ollama-stop')"

clean: ## Stop and remove containers + volumes (DELETES ALL DATA)
	docker compose down -v
	@echo "All containers and volumes removed."

logs: ## Tail all service logs
	docker compose logs -f

restart: ## Restart all services
	docker compose restart

# === Database ===
migrate: ## Run database migrations
	docker compose run --rm ekamcore-migrate

migration: ## Create new migration (usage: make migration name=add_users)
	cd apps/api && poetry run alembic revision --autogenerate -m "$(name)"

seed: ## Seed database with dev data
	docker compose exec ekamcore-api python -m scripts.seed

# === Testing ===
test: test-api test-web test-mobile ## Run all tests

test-api: ## Run API tests with coverage
	cd apps/api && poetry run pytest -v --tb=short --cov=api --cov-report=term-missing

test-web: ## Run web tests
	cd apps/web && pnpm test 2>/dev/null || echo "No web tests yet"

test-mobile: ## Run mobile tests
	cd apps/mobile && npx jest --passWithNoTests

test-integration: ## Run integration tests (requires Docker)
	docker compose -f docker-compose.test.yml up -d
	cd apps/api && poetry run pytest tests/integration -v
	docker compose -f docker-compose.test.yml down

coverage: ## Run tests with HTML coverage report
	cd apps/api && poetry run pytest --cov=api --cov-report=html --cov-report=term

# === Code Quality ===
lint: ## Run all linters
	cd apps/api && poetry run ruff check .
	cd apps/web && pnpm lint 2>/dev/null || true
	cd apps/mobile && npx eslint src --ext .ts,.tsx 2>/dev/null || true

format: ## Format all code
	cd apps/api && poetry run ruff format .
	cd apps/web && pnpm format 2>/dev/null || true

# === Benchmarks ===
benchmark: ## Run performance benchmarks
	cd apps/api && poetry run python ../../scripts/benchmark/run_all.py

# === Shell Access ===
shell-api: ## Shell into API container
	docker compose exec ekamcore-api bash

shell-db: ## Shell into PostgreSQL
	docker compose exec ekamcore-postgres psql -U ekamcore -d ekamcore

shell-redis: ## Shell into Redis CLI
	docker compose exec ekamcore-redis redis-cli -a $${REDIS_PASSWORD:-ekamcore_redis_dev}

# === Ollama (native on host) ===
ollama-start: ## Start Ollama natively on host
	@if ! pgrep -x ollama > /dev/null 2>&1; then \
		echo "Starting Ollama..."; \
		ollama serve > /dev/null 2>&1 & \
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

paperless-token: ## Create Paperless API token for admin (idempotent — returns existing token if already created)
	@docker compose exec ekamcore-paperless python3 manage.py drf_create_token admin

paperless-shell: ## Shell into PaperlessNGX container
	docker compose exec ekamcore-paperless bash

# === Backup / Restore ===
backup: ## Run backup (pg_dump + Qdrant snapshots + Paperless export + config)
	@BACKUP_DIR="$${EKAMCORE_BACKUP_DIR:-/backups}" bash infra/backup/backup.sh

restore: ## Restore from backup (usage: make restore BACKUP_PATH=/backups/2026-04-10_02-00-00)
	@if [ -z "$(BACKUP_PATH)" ]; then \
		echo "ERROR: BACKUP_PATH is required. Usage: make restore BACKUP_PATH=/backups/2026-04-10_02-00-00"; \
		exit 1; \
	fi
	bash infra/backup/restore.sh "$(BACKUP_PATH)"

backup-list: ## List available backups with sizes
	@BACKUP_DIR="$${EKAMCORE_BACKUP_DIR:-/backups}"; \
	if [ ! -d "$$BACKUP_DIR" ]; then \
		echo "No backups directory found at $$BACKUP_DIR"; \
		exit 0; \
	fi; \
	echo "Available backups in $$BACKUP_DIR:"; \
	ls -lt "$$BACKUP_DIR" | grep "^d" | awk '{print $$NF}' | while read -r dir; do \
		size=$$(du -sh "$$BACKUP_DIR/$$dir" 2>/dev/null | cut -f1); \
		echo "  $$dir  ($$size)"; \
	done

# === Local Development (without Docker) ===
dev-api: ## Run API in dev mode (local, no Docker)
	cd apps/api && poetry run uvicorn api.main:app --reload --host 0.0.0.0 --port 8420

dev-web: ## Run web in dev mode (local, no Docker)
	cd apps/web && pnpm dev

# === Help ===
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
