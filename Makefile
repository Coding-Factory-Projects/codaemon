.DEFAULT_GOAL := help

.SECTION: Code

.PHONY: install
install: ## Install project and development dependencies
	uv sync --all-groups

.PHONY: format
format: ## Format Python code with Ruff
	uv run ruff format src conftest.py

.PHONY: lint
lint: ## Lint and type-check Python code
	uv run ruff check src conftest.py
	uv run ty check src

.PHONY: check
check: ## Run Django system checks
	.venv/bin/python manage.py check

.PHONY: help
help:
	@awk 'BEGIN {FS = ":.*?## "; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^\.SECTION:/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 11) } \
		/^[a-zA-Z_-]+:.*?## / { printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
