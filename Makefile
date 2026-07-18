.PHONY: install test lint check-all schemas smoke

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src

check-all: lint test

schemas:
	uv run python scripts/export_schemas.py

smoke:
	@echo "smoke target: not implemented (requires AUTOGOVERN_SMOKE=1 and provider config)"
