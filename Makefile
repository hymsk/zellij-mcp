PYTHON ?= python3

.PHONY: dev-install run compile test test-cov docs-check diff-check \
	check lint lint-fix verify typecheck security audit integration-smoke \
	integration-installed integration-isolated integration-tab integration-pane \
	integration-safety clean

dev-install:
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(PYTHON) -m zellij_mcp serve

compile:
	$(PYTHON) -m compileall -q zellij_mcp tests scripts

test:
	$(PYTHON) -m pytest tests/unit -v

test-cov:
	$(PYTHON) -m pytest tests/unit -v --cov=zellij_mcp --cov-report=term-missing \
		--cov-fail-under=75

docs-check:
	$(PYTHON) scripts/check_docs.py

diff-check:
	git diff --check -- .

check: compile test docs-check diff-check

lint:
	ruff check zellij_mcp/ tests/ scripts/

lint-fix:
	ruff check --fix zellij_mcp/ tests/ scripts/

verify: lint check

typecheck:
	mypy zellij_mcp/

security:
	bandit -r zellij_mcp scripts --severity-level medium

audit: verify test-cov typecheck security

integration-smoke:
	$(PYTHON) tests/integration/server_smoke.py

integration-installed:
	$(PYTHON) tests/integration/installed_wheel_smoke.py

integration-isolated:
	$(PYTHON) tests/integration/zellij_isolated_lifecycle.py

integration-tab:
	$(PYTHON) tests/integration/zellij_tab_lifecycle.py

integration-pane:
	$(PYTHON) tests/integration/zellij_pane_lifecycle.py

integration-safety:
	$(PYTHON) tests/integration/zellij_pane_safety.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage coverage.xml \
		coverage.json bandit.json bandit-full.json build dist
