# Agent Tag — developer tasks.
# `make help` lists targets. Everything assumes an activated venv.

.DEFAULT_GOAL := help
.PHONY: help install test lint fmt serve run clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Editable install with all extras + dev/test deps
	pip install -e '.[all,dev]'

test: ## Run the test suite
	pytest

lint: ## Lint with ruff (check only)
	ruff check .

fmt: ## Format the codebase with ruff
	ruff format .

serve: ## Run the admin console + adapters + ambient (http://localhost:8765)
	agent-tag serve

run: ## Zero-credential local demo (console adapter, echo backend)
	agent-tag run --adapter console --backend echo

clean: ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
