.DEFAULT_GOAL := help

.SECTION: Environment

ANSIBLE_PLAYBOOK := ansible-playbook

.PHONY: dev
dev: ## Render the local .env from Ansible and 1Password
	$(ANSIBLE_PLAYBOOK) --connection=local --inventory ansible/inventories/dev \
		--extra-vars "deploy_env=dev" --tags dev ansible/site.yml

.PHONY: configure-int
configure-int: ## Install the int application directory and Nginx configuration
	$(ANSIBLE_PLAYBOOK) --inventory ansible/inventories/int \
		--extra-vars "deploy_env=int" --tags configure ansible/site.yml

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
