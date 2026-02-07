# Codebase Structure

**Analysis Date:** 2026-02-06

## Directory Layout

```
lattice/
├── src/lattice/                    # Main package source
│   ├── __init__.py                 # Public API exports
│   ├── asset.py                    # @asset decorator
│   ├── executor.py                 # Executor and AsyncExecutor
│   ├── graph.py                    # DependencyGraph
│   ├── models.py                   # AssetKey, AssetDefinition
│   ├── plan.py                     # ExecutionPlan
│   ├── registry.py                 # AssetRegistry
│   ├── exceptions.py               # CyclicDependencyError
│   ├── cli.py                      # Command-line interface
│   ├── io/                         # Storage backends
│   │   ├── __init__.py
│   │   ├── base.py                 # IOManager ABC
│   │   ├── memory.py               # MemoryIOManager
│   │   ├── file.py                 # FileIOManager
│   │   └── parquet.py              # ParquetIOManager (optional)
│   ├── logging/                    # Logging setup
│   │   ├── __init__.py
│   │   └── config.py               # configure_logging()
│   ├── observability/              # Observability features
│   │   ├── __init__.py
│   │   ├── models.py               # CheckResult, LogEntry, LineageEvent, RunResult, RunRecord
│   │   ├── checks.py               # CheckDefinition, CheckRegistry, AssetWithChecks
│   │   ├── lineage.py              # LineageTracker, LineageIOManager
│   │   ├── log_capture.py          # LogCapture handler
│   │   ├── history/                # Run history storage
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # RunHistoryStore ABC
│   │   │   └── sqlite.py           # SQLiteRunHistoryStore
│   ├── web/                        # Web visualization
│   │   ├── __init__.py
│   │   ├── app.py                  # create_app() factory
│   │   ├── routes.py               # Graph/asset endpoints
│   │   ├── routes_history.py       # Run history endpoints
│   │   ├── execution.py            # ExecutionManager, WebSocket handling
│   │   ├── schemas.py              # Graph schema models
│   │   ├── schemas_execution.py    # Execution schema models
│   │   ├── templates/              # Jinja2 HTML templates
│   │   │   ├── index.html
│   │   │   └── asset_detail.html
│   │   └── static/                 # CSS and JavaScript
│   │       ├── css/                # Stylesheets
│   │       └── js/                 # D3.js visualization, WebSocket client
├── tests/                          # Test suite
│   ├── conftest.py                 # Shared pytest fixtures
│   ├── test_asset.py               # @asset decorator tests
│   ├── test_executor.py            # Executor tests
│   ├── test_graph.py               # DependencyGraph tests
│   ├── test_plan.py                # ExecutionPlan tests
│   ├── test_io.py                  # IO manager tests
│   ├── test_cli.py                 # CLI tests
│   ├── test_web.py                 # Web service tests
│   └── test_observability/         # Observability feature tests
│       ├── test_checks.py          # Check definition and execution
│       ├── test_lineage.py         # Lineage tracking
│       ├── test_log_capture.py     # Log capture handler
│       ├── test_history_sqlite.py  # History store
│       ├── test_models.py          # Observability models
│       └── test_integration.py     # Full observability integration
├── examples/                       # Example scripts
│   └── web_demo.py                 # Web service demo
├── pyproject.toml                  # Project metadata, dependencies, entry points
├── README.md                       # User documentation
├── CHANGELOG.md                    # Release history
└── PROJECT_PLAN.md                 # Development roadmap
```

## Directory Purposes

**src/lattice/:**
- Purpose: Core framework package; everything users import from `lattice.*`
- Contains: Asset declaration, execution engine, registry, IO abstraction, observability, web service, CLI
- Key files: `__init__.py` (public API), `models.py` (core data structures), `executor.py` (execution engine)

**src/lattice/io/:**
- Purpose: Pluggable asset storage backends
- Contains: Abstract IOManager, in-memory storage, file-based storage, Parquet support
- Key files: `base.py` (ABC), `memory.py` (default for testing), `file.py` (local filesystem)

**src/lattice/logging/:**
- Purpose: Isolated logging configuration layer
- Contains: Setup function to enable Python logging
- Key files: `config.py` (configure_logging implementation)

**src/lattice/observability/:**
- Purpose: Optional observability features (logs, lineage, checks, run history)
- Contains: Data quality check definitions, log capture, lineage tracking, persistent history storage
- Key files: `models.py` (RunResult, RunRecord), `checks.py` (CheckRegistry), `history/sqlite.py` (storage)

**src/lattice/web/:**
- Purpose: FastAPI web service for visualization and execution monitoring
- Contains: Graph visualization API, execution control endpoints, WebSocket push updates, HTML templates, static assets
- Key files: `app.py` (FastAPI factory), `routes.py` (graph endpoints), `execution.py` (state management)

**tests/:**
- Purpose: Test suite using pytest
- Contains: Unit tests for each module, integration tests, fixtures
- Key files: `conftest.py` (global fixtures like clean_global_registries), test files mirror src/ structure

**examples/:**
- Purpose: User-facing example scripts and demos
- Contains: web_demo.py showing web service usage
- Key files: `web_demo.py` (FastAPI + uvicorn demo)

## Key File Locations

**Entry Points:**

- `src/lattice/__init__.py`: Main public API (asset, materialize, ExecutionPlan, etc.)
- `src/lattice/cli.py`: CLI entry point (registered in pyproject.toml as `lattice` command)
- `src/lattice/web/app.py`: Web service entry (create_app factory)

**Core Models:**

- `src/lattice/models.py`: AssetKey, AssetDefinition
- `src/lattice/observability/models.py`: CheckResult, LogEntry, LineageEvent, RunResult, RunRecord

**Asset Declaration:**

- `src/lattice/asset.py`: @asset decorator, _extract_dependencies(), _extract_return_type()
- `src/lattice/registry.py`: AssetRegistry for storing definitions

**Graph & Planning:**

- `src/lattice/graph.py`: DependencyGraph, topological_sort() via Kahn's algorithm
- `src/lattice/plan.py`: ExecutionPlan.resolve() for creating execution plans

**Execution:**

- `src/lattice/executor.py`: Executor (synchronous), AsyncExecutor (parallel), ExecutionState, ExecutionResult

**Storage:**

- `src/lattice/io/base.py`: IOManager abstract class
- `src/lattice/io/memory.py`: Default in-memory storage (dict-based)
- `src/lattice/io/file.py`: File system storage (pickle-based)
- `src/lattice/io/parquet.py`: Polars Parquet support (optional)

**Observability:**

- `src/lattice/observability/checks.py`: CheckDefinition, CheckRegistry, AssetWithChecks
- `src/lattice/observability/lineage.py`: LineageTracker, LineageIOManager
- `src/lattice/observability/log_capture.py`: LogCapture handler
- `src/lattice/observability/history/sqlite.py`: SQLiteRunHistoryStore

**Web:**

- `src/lattice/web/routes.py`: Graph visualization endpoints
- `src/lattice/web/execution.py`: ExecutionManager, execution control endpoints, WebSocket handling
- `src/lattice/web/schemas.py`: GraphSchema, NodeSchema, EdgeSchema, etc.

**Configuration:**

- `src/lattice/logging/config.py`: configure_logging() function

## Naming Conventions

**Files:**

- Modules: `snake_case.py` (e.g., `asset.py`, `log_capture.py`)
- Tests: `test_<module>.py` paired with `<module>.py` (e.g., `test_asset.py` for `asset.py`)
- Config files: `<name>.py` for Python modules, `*.toml` for configuration

**Directories:**

- Package directories: `snake_case` (e.g., `observability/`, `web/`)
- Feature groupings: Logical packages with `__init__.py` (e.g., `io/`, `logging/`)

**Classes:**

- Data models: `PascalCase` (e.g., AssetKey, ExecutionResult)
- Enum classes: `PascalCase` (e.g., AssetStatus, CheckStatus)
- Managers/registries: `PascalCase` (e.g., AssetRegistry, ExecutionManager)
- Abstract bases: `PascalCase` with suffix ABC (e.g., IOManager despite being abstract, RunHistoryStore)

**Functions:**

- Public: `snake_case` (e.g., materialize, topological_sort)
- Private (module-level): `_snake_case` (e.g., _extract_dependencies)
- Decorators: `snake_case` (e.g., @asset, @check)

**Variables:**

- Constants: `UPPER_CASE` (e.g., in config files)
- Parameters/locals: `snake_case`
- Type variables: `PascalCase` (e.g., T, P, R)

## Where to Add New Code

**New Feature (e.g., a new dependency resolution strategy):**
- Primary code: `src/lattice/graph.py` (extend DependencyGraph) or new file `src/lattice/strategy.py`
- Tests: `tests/test_graph.py` or `tests/test_strategy.py`
- Entry point: Export from `src/lattice/__init__.py` if public

**New IO Manager (e.g., PostgreSQL backend):**
- Implementation: `src/lattice/io/postgres.py` (subclass IOManager)
- Tests: `tests/test_io.py` (add test cases) or `tests/test_postgres_io.py`
- Optional export: If optional dependency, conditionally import in `src/lattice/io/__init__.py` like ParquetIOManager

**New Web Route (e.g., asset metrics endpoint):**
- Implementation: `src/lattice/web/routes.py` (add endpoint to router created by create_router)
- Schema: Add Pydantic model to `src/lattice/web/schemas.py`
- Tests: `tests/test_web.py` (add test case)
- Template: If HTML, add to `src/lattice/web/templates/`

**New Observability Feature (e.g., cost tracking):**
- Models: Add dataclass/Pydantic to `src/lattice/observability/models.py`
- Logic: New file `src/lattice/observability/costs.py` (or extend existing)
- Integration: Update `materialize_with_observability()` in `src/lattice/observability/__init__.py`
- Tests: `tests/test_observability/test_costs.py`

**New Utilities/Helpers:**
- Shared helpers: `src/lattice/utils.py` (if small) or `src/lattice/utils/` package (if large)
- Tests: `tests/test_utils.py` (mirror the structure)

**New CLI Command:**
- Implementation: Add command function to `src/lattice/cli.py`
- Tests: `tests/test_cli.py` (add test for command)

## Special Directories

**src/lattice/__pycache__/, tests/__pycache__/, etc.:**
- Purpose: Compiled Python bytecode (generated)
- Generated: Yes (by Python import system)
- Committed: No (in .gitignore)

**.pytest_cache/, .mypy_cache/, .ruff_cache/:**
- Purpose: Tool caches (pytest, mypy, ruff)
- Generated: Yes (by tools during development)
- Committed: No (in .gitignore)

**src/lattice/web/static/, src/lattice/web/templates/:**
- Purpose: Frontend assets (JavaScript, CSS, HTML)
- Generated: No (manually created)
- Committed: Yes (part of web service)

**.planning/codebase/:**
- Purpose: GSD planning documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
- Generated: Yes (by GSD mapper)
- Committed: Yes (used by GSD executor)

## Module Dependencies

**Layers (top depends on bottom):**

1. Web layer (`src/lattice/web/`) depends on: executor, registry, observability, models
2. CLI layer (`src/lattice/cli.py`) depends on: observability.history
3. Observability layer (`src/lattice/observability/`) depends on: executor, io.base, models
4. Executor layer (`src/lattice/executor.py`) depends on: plan, io.base, models
5. Planning layer (`src/lattice/plan.py`, `src/lattice/graph.py`) depends on: registry, models
6. Registry layer (`src/lattice/registry.py`) depends on: models
7. Asset/Declaration layer (`src/lattice/asset.py`) depends on: registry, models
8. Core layer (`src/lattice/models.py`, `src/lattice/exceptions.py`) depends on: nothing
9. IO layer (`src/lattice/io/`) depends on: models
10. Logging layer (`src/lattice/logging/`) depends on: nothing

**Circular dependency avoidance:**
- `executor.py` uses `TYPE_CHECKING` to import AssetRegistry only for type hints, breaking the cycle with registry.py
- `asset.py` uses `TYPE_CHECKING` to import AssetWithChecks only for type hints, breaking the cycle with observability.checks
- All modules use `from __future__ import annotations` to enable postponed evaluation of type hints

## Public API Surface

Exported from `src/lattice/__init__.py`:

- `asset` (decorator)
- `AssetDefinition`, `AssetKey`
- `AssetRegistry`, `get_global_registry`
- `DependencyGraph`, `ExecutionPlan`
- `Executor`, `AsyncExecutor`, `ExecutionResult`, `ExecutionState`, `AssetStatus`, `AssetExecutionResult`
- `materialize`, `materialize_async`
- `IOManager`, `MemoryIOManager`, `FileIOManager`, `ParquetIOManager` (conditional)
- `configure_logging`, `get_logger`
- `AssetWithChecks`, `CheckDefinition`, `CheckRegistry`, `CheckStatus`, `CheckResult`
- `LineageEvent`, `LineageTracker`, `LineageIOManager`
- `LogEntry`, `RunHistoryStore`, `RunRecord`, `RunResult`, `SQLiteRunHistoryStore`
- `get_global_check_registry`, `materialize_with_observability`
- `CyclicDependencyError`

Users should import from `lattice` package, not internal submodules (e.g., `from lattice import asset` not `from lattice.asset import asset`).

---

*Structure analysis: 2026-02-06*
