.PHONY: gen editor test lint format clean requirements

gen:
	uv run python -m src

editor:
	uv run python -m src --editor

test:
	PYTHONPATH=. uv run python tests/test_engine.py

lint:
	uv run black --check . && uv run isort --check .

format:
	uv run black . && uv run isort .

clean:
	find generated/ -name "*.pdf" -delete 2>/dev/null || true

requirements:
	uv export --no-hashes --format requirements-txt > requirements.txt
