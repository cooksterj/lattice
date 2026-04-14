# List available recipes
default:
    @just --list

# Install dependencies
setup:
    uv sync

# Install with all extras (web demo, etc.)
setup-all:
    uv sync --all-extras

# Run tests (supports pass-through args, e.g. `just test -x -q -k test_name`)
test *args:
    uv run pytest {{ args }}

# Run tests with coverage report
cov:
    uv run pytest --cov --cov-report=term-missing

# Lint check
lint *args:
    uv run ruff check src tests {{ args }}

# Format code
format:
    uv run ruff format src tests

# Auto-fix lint issues and format
fix:
    uv run ruff check src tests --fix
    uv run ruff format src tests

# Run type checking
typecheck:
    uv run mypy src

# Run all static analysis (lint + typecheck)
check: lint typecheck

# Start web demo (localhost:8000)
demo:
    uv run python examples/web_demo.py

# Start lightweight demo for testing targeted execution (localhost:8000)
demo-lite:
    uv run python examples/web_demo_lite.py

# Clean build artifacts
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
