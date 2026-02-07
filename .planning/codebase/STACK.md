# Technology Stack

**Analysis Date:** 2026-02-06

## Languages

**Primary:**
- Python 3.11+ - Core framework, all orchestration logic, web server, and CLI

## Runtime

**Environment:**
- Python 3.11 (specified in `.python-version` and `pyproject.toml`)
- CPython

**Package Manager:**
- UV (modern Python package manager, replaces pip)
- Lockfile: `uv.lock` (present and committed)

## Frameworks

**Core:**
- Pydantic 2.12.5+ - Data validation and settings management for asset definitions and schemas
- Polars 1.0.0+ - DataFrames and tabular data processing

**Web/API:**
- FastAPI 0.115.0+ - REST API and web server framework
- Uvicorn 0.34.0+ - ASGI server runtime for FastAPI
- Jinja2 3.1.0+ - HTML template rendering for web visualization
- Starlette (via FastAPI) - Core web framework with WebSocket support

**Observability:**
- Python logging (standard library) - Built-in logging system
- SQLite (via sqlite3, standard library) - Run history persistence

**Testing:**
- Pytest 9.0.2+ - Test runner
- Pytest-asyncio 1.3.0+ - Async test support
- Hypothesis 6.151.2+ - Property-based testing
- HTTPx 0.28.0+ - HTTP client for testing

**Development:**
- MyPy 1.19.1+ - Static type checking
- Ruff 0.14.14+ - Linter and formatter
- Pre-commit 4.0.0+ - Git hooks for code quality

## Key Dependencies

**Critical:**
- `pydantic` (2.12.5+) - Defines all data models: AssetDefinition, AssetKey, RunRecord, CheckResult
- `polars` (1.0.0+) - DataFrame storage via ParquetIOManager; optional dependency loaded at runtime
- `fastapi` (0.115.0+) - Web API server for visualization and execution
- `uvicorn[standard]` (0.34.0+) - ASGI server with WebSocket support and uvloop

**Infrastructure:**
- `psutil` (5.9.0+) - System monitoring for memory snapshots in web execution API

**Optional (web extras):**
- `jinja2` (3.1.0+) - Template rendering for web UI
- `psutil` (5.9.0+) - Process memory tracking for execution monitoring

## Configuration

**Environment:**
- Single environment variable: `LATTICE_LOGGING_CONFIG`
  - Path to Python logging INI configuration file
  - Falls back to bundled default at `src/lattice/logging/logging.conf`
  - If not provided, uses basic `logging.basicConfig`

**Build:**
- `pyproject.toml` - Project metadata, dependencies, and tool configuration
  - Uses Hatchling as build backend
  - Defines three dependency groups: core, optional `web`, and `dev`

**Linting/Formatting:**
- `.ruff.toml` or `[tool.ruff]` section in `pyproject.toml`:
  - Line length: 100 characters
  - Target Python: 3.11
  - Rules: E (errors), F (Pyflakes), I (imports), UP (upgrades), B (flake8-bugbear), SIM (simplification), PTH (pathlib)

**Type Checking:**
- `[tool.mypy]` in `pyproject.toml`:
  - Strict mode enabled
  - Python version: 3.11

**Testing:**
- `[tool.pytest.ini_options]` in `pyproject.toml`:
  - Test path: `tests/`
  - asyncio_mode: auto (handles async test discovery automatically)

## Database Storage

**Persistent History:**
- SQLite database (default: `lattice_runs.db` in working directory)
- Stores run records, logs, lineage events, check results, and asset results
- Schema defined in `src/lattice/observability/history/sqlite.py`

**Asset Data Storage:**
- Memory (MemoryIOManager) - For testing/temporary runs
- Filesystem pickle files (FileIOManager) - Default for persistent storage
- Apache Parquet (ParquetIOManager) - Optional for Polars DataFrames; lazy-loaded

## Platform Requirements

**Development:**
- Python 3.11 or higher
- Git (for pre-commit hooks)
- Any OS: macOS, Linux, Windows (cross-platform)

**Production/Web Server:**
- Python 3.11 or higher
- Uvicorn ASGI server (included in dependencies)
- Access to filesystem for SQLite database and asset storage
- Optional: psutil for memory monitoring

---

*Stack analysis: 2026-02-06*
