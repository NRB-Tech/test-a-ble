.PHONY: clean clean-test clean-pyc clean-build docs help
.DEFAULT_GOAL := help

# If NO_UV is set, don't use uv to run commands
ifdef NO_UV
	PY_CMD_PREFIX :=
else
	PY_CMD_PREFIX := uv run
endif

define BROWSER_PYSCRIPT
import os, webbrowser, sys

try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

BROWSER := $(PY_CMD_PREFIX) python -c "$$BROWSER_PYSCRIPT"

help:
	@$(PY_CMD_PREFIX) python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -fr .pytest_cache
	rm -fr .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache/

lint: ## check style
	$(PY_CMD_PREFIX) ruff check .
	$(PY_CMD_PREFIX) ruff format --check .

format: ## format code
	$(PY_CMD_PREFIX) ruff format .
	$(PY_CMD_PREFIX) ruff check --fix .

typecheck: ## type check code
	$(PY_CMD_PREFIX) mypy

bandit: ## run bandit security checks
	$(PY_CMD_PREFIX) bandit -c pyproject.toml -r .

safety: ## run safety checks
	$(PY_CMD_PREFIX) safety scan

security: bandit safety ## run security checks

pre-commit: ## run pre-commit checks
	$(PY_CMD_PREFIX) pre-commit run --all-files

test: ## run tests quickly with the default Python
	$(PY_CMD_PREFIX) pytest

check: ## run all checks
	$(PY_CMD_PREFIX) tox

coverage: ## check code coverage quickly with the default Python
	$(PY_CMD_PREFIX) coverage run --source test_a_ble -m pytest
	$(PY_CMD_PREFIX) coverage report -m
	$(PY_CMD_PREFIX) coverage html
	$(BROWSER) htmlcov/index.html

docs: ## generate Sphinx HTML documentation, including API docs
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/build/html/index.html

servedocs: docs ## compile the docs watching for changes
	$(PY_CMD_PREFIX) watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

build: clean ## builds source and wheel package
	$(PY_CMD_PREFIX) python -m build

install: clean ## install the package to the active Python's site-packages
ifdef USE_UV
	uv sync --no-default-groups
else
	pip install -e .
endif

dev-install: clean ## install the package and development dependencies. When using uv, dev dependencies are installed by default.
ifdef USE_UV
	uv sync
else
	pip install -e ".[dev]"
endif
