# Lattice

An asset-centric orchestration framework inspired by Dagster's design philosophy.

## Why Lattice?

If you've chained shell scripts together for data pipelines, you've likely hit these limitations:

| Concern | Shell Scripts | Lattice |
|---------|---------------|---------|
| **Dependencies** | Linear chains only | Complex DAGs (diamonds, fan-out/fan-in) |
| **Parallelism** | Manual with `&` and `wait` | Automatic based on DAG structure |
| **Partial runs** | All or nothing | Run single asset + its dependencies |
| **Failure handling** | `set -e` stops everything | Skip downstream, continue independent branches |
| **Observability** | Custom logging | Built-in status, timing, run history |
| **Caching** | DIY file checks | IO managers handle storage/retrieval |
| **Testing** | Difficult to unit test | Standard Python functions |

The key insight is the **DAG model**: you declare what depends on what, and the framework handles execution order, parallelism, and failure propagation.

```python
from lattice import asset, materialize

@asset
def raw_data() -> list:
    return fetch_from_api()

@asset
def cleaned_data(raw_data: list) -> list:
    return [clean(r) for r in raw_data]

@asset
def report(cleaned_data: list) -> dict:
    return generate_report(cleaned_data)

# Run everything, or just what's needed for a specific target
materialize()                    # all assets
materialize(target="report")     # report + dependencies only
```

## Installation

Python 3.11 or later is required.

```bash
# Core library
pip install lattice

# With web UI and server
pip install lattice[web]
```

## Quick Start

Define assets as decorated Python functions. Dependencies are declared via the `deps` parameter; when omitted the asset is treated as a source with no upstream dependencies.

```python
# pipeline.py
from lattice import asset, materialize

@asset
def users() -> list[dict]:
    """Fetch raw user records."""
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

@asset(deps=["users"])
def active_users(users: list[dict]) -> list[dict]:
    """Filter to active users only."""
    return [u for u in users if u.get("active", True)]

@asset(deps=["active_users"])
def user_report(active_users: list[dict]) -> dict:
    """Build a summary report."""
    return {"total": len(active_users), "users": active_users}

# Run the full pipeline
result = materialize()

# Or materialize a single target (only runs its dependencies)
result = materialize(target="user_report")
```

## Asset Groups and Checks

Use `group` to organise related assets and `.check()` to attach data-quality validations.

```python
from lattice import asset

@asset(group="ingestion")
def raw_orders() -> list[dict]:
    return load_orders_from_source()

@raw_orders.check("non-empty", description="At least one order")
def check_raw_orders(result: list[dict]) -> bool:
    return len(result) > 0

@asset(group="ingestion", deps=["raw_orders"])
def cleaned_orders(raw_orders: list[dict]) -> list[dict]:
    return [o for o in raw_orders if o.get("amount", 0) > 0]
```

Checks run automatically after an asset materializes. Failed checks are recorded in run history and surfaced in the web UI.

## Run History

Lattice persists every pipeline run in a local SQLite database. No external database server or migrations are required — `SQLiteRunHistoryStore` creates the database file and table on first use.

By default the database is written to `data/lattice_runs.db` relative to the working directory. Set the `LATTICE_DB_PATH` environment variable to relocate it — useful when deploying to Docker, ECS, or any environment where the default relative path isn't appropriate.
```python
from lattice import materialize_with_observability, SQLiteRunHistoryStore

store = SQLiteRunHistoryStore()  # uses LATTICE_DB_PATH or data/lattice_runs.db

result = materialize_with_observability(history_store=store)
```

### CLI

The `lattice` command (installed automatically via `pip install lattice`) provides quick access to run history.

```bash
# List recent runs
lattice list
lattice list --limit 5 --status failed

# Show details of a specific run
lattice show <run_id>
lattice show <run_id> --all          # include logs, checks, lineage, assets
lattice show <run_id> --assets       # asset-level results only
lattice show <run_id> --logs         # captured log output
lattice show <run_id> --checks       # check results
lattice show <run_id> --lineage      # lineage events

# Delete a single run
lattice delete <run_id>

# Clear all history
lattice clear              # interactive confirmation
lattice clear --force      # skip confirmation
```

All commands accept `--db <path>` to point at a non-default database file.

## Web UI

Install with the `web` extra and start the server:

```python
from lattice import SQLiteRunHistoryStore
from lattice.web import serve

store = SQLiteRunHistoryStore()
serve(history_store=store)   # binds to LATTICE_HOST:LATTICE_PORT (default 127.0.0.1:8000)
```

Then open http://localhost:8000 in your browser.

https://github.com/user-attachments/assets/28762d8f-c9cb-4737-884c-5fd49d7be8c5

### Pages

| Route | Description |
|-------|-------------|
| `/` | Groups overview — high-level view of asset groups |
| `/pipeline` | Full pipeline DAG visualization |
| `/group/{name}` | Detail view for a single asset group |
| `/assets` | Asset catalog with search and filtering |
| `/runs` | Active run monitoring |
| `/history` | Run history browser |

### Features

- Left-to-right hierarchical layout showing dependency flow
- Interactive nodes (click for details, drag to reposition)
- Dependency highlighting on hover
- Dark/light theme toggle

## Configuration

Lattice reads `LATTICE_*` environment variables so it can be configured externally (e.g. in Docker, ECS, EC2) without modifying code.

| Variable | Description | Default |
|----------|-------------|---------|
| `LATTICE_HOST` | Web server bind address | `127.0.0.1` |
| `LATTICE_PORT` | Web server port | `8000` |
| `LATTICE_DB_PATH` | Path to SQLite run-history database | `data/lattice_runs.db` |
| `LATTICE_MAX_CONCURRENCY` | Max concurrent asset executions | `4` |
| `LATTICE_LOGGING_CONFIG` | Path to custom logging config file (INI format) | *(none)* |

## Logging

Lattice uses Python's standard logging module. By default, logging is not configured (no output). You can enable it explicitly:

```python
from lattice import configure_logging

configure_logging()  # Uses bundled default config (INFO level)
```

### Customization Options

**Option 1: Environment variable**
```bash
export LATTICE_LOGGING_CONFIG=/path/to/custom.conf
python my_pipeline.py
```

**Option 2: Programmatic path**
```python
from lattice import configure_logging

configure_logging("/path/to/custom.conf")
```

**Option 3: Standard logging (bypass Lattice config)**
```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

### Configuration Format

The config file uses Python's INI-based [logging.config.fileConfig](https://docs.python.org/3/library/logging.config.html#logging.config.fileConfig) format. See `src/lattice/logging/logging.conf` for the default configuration.

### Log Levels

| Level | What's Logged |
|-------|---------------|
| DEBUG | Dependency details, IO operations, graph algorithm steps |
| INFO | Asset registration, execution start/complete, server startup |
| WARNING | Cycle detection, missing assets |
| ERROR | Execution failures with stack traces |

## Docker

```bash
# Build the image
docker build -t lattice .

# Run with a persistent volume for the SQLite database
docker run -p 8000:8000 -v ./data:/app/data lattice
```

Or use Docker Compose:

```bash
docker compose up
```

The Compose file mounts `./data` into the container so run history survives restarts. See `docker-compose.yml` for the full configuration.

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src tests

# Run type checker
uv run mypy src
```
