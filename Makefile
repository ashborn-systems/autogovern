.PHONY: install test lint check-all schemas smoke build

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

build:
	uv build

smoke:
	@echo "smoke target: requires AUTOGOVERN_SMOKE=1 and a configured provider"
	@echo "Set AUTOGOVERN_API_BASE, AUTOGOVERN_MODEL, AUTOGOVERN_API_KEY_ENV"
	@echo "then run: AUTOGOVERN_SMOKE=1 uv run pytest tests/test_smoke.py"
