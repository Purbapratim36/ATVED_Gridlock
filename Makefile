.PHONY: help install dev test lint format run worker docker-up docker-down migrate db-upgrade db-downgrade

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

dev: ## Install all dependencies (dev + ml + mlops)
	pip install -e ".[dev,ml,mlops]"

test: ## Run tests
	pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests
	pytest tests/integration/ -v --tb=short -m integration

test-fairness: ## Run fairness/bias tests
	pytest tests/fairness/ -v --tb=short -m fairness

test-cov: ## Run tests with coverage
	pytest tests/ --cov=atved --cov-report=html --cov-report=term-missing

lint: ## Run linter
	ruff check src/ tests/
	mypy src/atved/

format: ## Format code
	ruff format src/ tests/
	ruff check --fix src/ tests/

run: ## Run API server (development)
	uvicorn atved.api.main:create_app --factory --reload --host 0.0.0.0 --port 8000

worker: ## Run inference worker
	python -m atved.workers.inference_worker

retention-worker: ## Run retention cleanup worker
	python -m atved.workers.retention_worker

docker-up: ## Start local development stack
	docker compose up -d

docker-down: ## Stop local development stack
	docker compose down

docker-build: ## Build Docker images
	docker compose build

migrate: ## Create a new migration
	alembic -c src/atved/db/alembic.ini revision --autogenerate -m "$(MSG)"

db-upgrade: ## Apply all pending migrations
	alembic -c src/atved/db/alembic.ini upgrade head

db-downgrade: ## Rollback last migration
	alembic -c src/atved/db/alembic.ini downgrade -1

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
