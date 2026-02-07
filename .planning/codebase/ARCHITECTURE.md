# Architecture

**Analysis Date:** 2026-02-06

## Pattern Overview

**Overall:** Asset-centric directed acyclic graph (DAG) orchestration framework with pluggable storage backends and optional observability layer.

**Key Characteristics:**
- **Asset-driven design**: Core concept is the asset—a function that computes and stores a value, with explicit dependencies on other assets
- **Declarative dependencies**: Asset dependencies are inferred from function parameter names, creating automatic DAG construction
- **Topological execution**: Assets execute in order determined by Kahn's algorithm, ensuring dependencies complete before dependents
- **Pluggable IO**: Abstract IOManager interface allows different storage backends (memory, files, Parquet, databases)
- **Observability as layers**: Logging, lineage tracking, checks, and history can wrap execution without coupling to core
- **Async-first execution**: AsyncExecutor enables parallel asset materialization; synchronous Executor available for simpler cases

## Layers

**Registry Layer:**
- Purpose: Store asset definitions and check definitions in global or isolated registries
- Location: `src/lattice/registry.py`, `src/lattice/observability/checks.py`
- Contains: AssetRegistry (maps AssetKey → AssetDefinition), CheckRegistry (maps AssetKey → list of CheckDefinition)
- Depends on: models.py
- Used by: All higher layers (executor, planner, web service)

**Declaration Layer:**
- Purpose: Provide @asset decorator API for users to define assets and attach checks
- Location: `src/lattice/asset.py`, `src/lattice/observability/checks.py` (AssetWithChecks class)
- Contains: @asset decorator, dependency extraction logic, @check decorator
- Depends on: models.py, registry.py
- Used by: User code; decorators register to global registry by default

**Graph & Planning Layer:**
- Purpose: Build dependency graph from registry, perform topological sort, create execution plans
- Location: `src/lattice/graph.py`, `src/lattice/plan.py`
- Contains: DependencyGraph (immutable graph with forward/reverse edges), ExecutionPlan (ordered asset list)
- Depends on: registry.py, models.py
- Used by: Executor; CLI for targeting specific assets

**Execution Layer:**
- Purpose: Walk an ExecutionPlan, load dependencies via IO managers, invoke asset functions, store results
- Location: `src/lattice/executor.py`
- Contains: Executor (synchronous), AsyncExecutor (asynchronous), ExecutionState (mutable during run), ExecutionResult (immutable summary)
- Depends on: plan.py, io/base.py, models.py
- Used by: materialize() functions, web service; can be wrapped by observability layer

**IO Layer:**
- Purpose: Abstract asset storage and retrieval across different backends
- Location: `src/lattice/io/base.py`, `src/lattice/io/memory.py`, `src/lattice/io/file.py`, `src/lattice/io/parquet.py`
- Contains: IOManager ABC (load/store/has/delete), MemoryIOManager, FileIOManager, ParquetIOManager, LineageIOManager (wraps another manager)
- Depends on: models.py
- Used by: Executor to persist asset values; tests commonly use MemoryIOManager

**Observability Layer:**
- Purpose: Capture logs, track lineage, run data quality checks, store run history
- Location: `src/lattice/observability/` subdirectory
- Contains:
  - `log_capture.py`: LogCapture handler intercepts Python logging during execution
  - `lineage.py`: LineageTracker records read/write events via LineageIOManager wrapper
  - `checks.py`: CheckRegistry and CheckDefinition for data quality checks
  - `models.py`: CheckResult, LogEntry, LineageEvent, RunResult, RunRecord
  - `history/`: RunHistoryStore ABC and SQLiteRunHistoryStore for persistent storage
- Depends on: executor.py, io/base.py, models.py
- Used by: materialize_with_observability() wraps execution; web service

**Web Layer:**
- Purpose: FastAPI service for visualizing asset graph and running/monitoring executions
- Location: `src/lattice/web/` subdirectory
- Contains:
  - `app.py`: FastAPI app factory, mounts routers and static files
  - `routes.py`: Graph visualization endpoints (/api/graph, /asset detail pages)
  - `execution.py`: ExecutionManager tracks running executions, WebSocket push updates
  - `routes_history.py`: Run history query endpoints
  - `schemas.py`, `schemas_execution.py`: Pydantic response models
  - `templates/`: Jinja2 HTML templates (index.html, asset_detail.html)
  - `static/`: CSS and JavaScript for D3.js visualization and WebSocket client
- Depends on: executor.py, registry.py, observability.py, models.py
- Used by: Optional enhancement; users run create_app() and serve with uvicorn

**Logging Layer:**
- Purpose: Provide configurable logging setup independent of execution
- Location: `src/lattice/logging/`
- Contains: configure_logging() function to enable/configure Python logging from file or environment
- Depends on: None (isolated)
- Used by: User code before defining assets

**CLI Layer:**
- Purpose: Command-line interface for querying run history
- Location: `src/lattice/cli.py`
- Contains: argparse-based CLI (list, show, delete runs)
- Depends on: observability/history.py
- Used by: Terminal users via `lattice` command (installed via pyproject.toml entry point)

## Data Flow

**Asset Definition & Registration:**

1. User decorates function with `@asset` (or `@asset_group(...).asset`)
2. `_extract_dependencies()` introspects function signature, converts param names to AssetKey objects
3. `_extract_return_type()` captures return type annotation
4. AssetDefinition is created with key, function, dependencies, return type
5. Decorator registers AssetDefinition to global registry (or specified registry)
6. If using checks, decorator wraps AssetDefinition in AssetWithChecks to enable `.check()` method

**Execution Plan Creation:**

1. User calls `ExecutionPlan.resolve(registry, target="some_asset")`
2. Plan builder creates DependencyGraph from registry
3. Topological sort (Kahn's algorithm) orders assets so dependencies come first
4. If target specified, plan filters to only required assets (upstream dependencies or downstream dependents)
5. ExecutionPlan returns immutable tuple of ordered AssetDefinitions

**Asset Execution (synchronous):**

1. User calls `materialize(plan, io_manager=...)`
2. Executor.execute(plan) creates ExecutionState, starts run
3. For each asset in plan:
   - Call on_asset_start callback
   - Load dependencies from io_manager using dependency_params to inject as kwargs
   - Call asset function with loaded dependencies
   - Store result in io_manager
   - Create AssetExecutionResult (key, status, timing, error if failed)
   - Call on_asset_complete callback
   - If failed, remaining assets are skipped
4. Return ExecutionResult with all asset results and summary (timing, counts)

**Asset Execution (asynchronous):**

1. User calls `materialize_async(plan, io_manager=...)`
2. AsyncExecutor.execute(plan) uses asyncio.gather to run multiple assets concurrently
3. Respects DAG ordering: only runs assets whose dependencies are complete
4. Uses semaphore to limit concurrency (default 4)
5. Returns ExecutionResult same as synchronous version

**Observability Wrapper:**

1. User calls `materialize_with_observability(plan, ..., history_store=...)`
2. Wraps execution with LogCapture (intercepts logging), LineageTracker, CheckRunner
3. During execution:
   - Logs captured to in-memory list
   - Asset reads/writes tracked via LineageIOManager wrapper
   - After asset completes, registered checks are run on its value
4. Returns RunResult (extends ExecutionResult with logs, lineage, check results)
5. If history_store provided, stores flattened RunRecord to persistent storage

**Web Visualization & Execution:**

1. User calls `create_app(registry, history_store=None)` → FastAPI instance
2. GET `/` serves index.html with D3.js visualization
3. GET `/api/graph` returns GraphSchema (nodes, edges) from DependencyGraph
4. User clicks "Execute" → POST `/api/execute/start` with target and partition_key
5. Execution runs in background (Executor or AsyncExecutor)
6. ExecutionManager tracks state, broadcasts updates via WebSocket to clients
7. Clients receive real-time asset completion events
8. GET `/asset/{key}` shows asset detail page with run history from history_store

**State Management:**

- **ExecutionState** (mutable): Tracks current_asset, counts, asset_results_dict during execution
- **ExecutionResult** (immutable): Summary after execution ends
- **RunRecord** (immutable): Flattened view persisted to database
- **ExecutionManager** (stateful): Holds dict[run_id] → ExecutionState for active runs in web service

## Key Abstractions

**AssetKey:**
- Purpose: Unique identifier for an asset (group-scoped name)
- Examples: `AssetKey(name="raw_data")`, `AssetKey(name="report", group="finance")`
- Pattern: Frozen Pydantic model; hashable (used as dict keys); __str__ formats as "group/name"
- Location: `src/lattice/models.py`

**AssetDefinition:**
- Purpose: Metadata wrapper pairing a function with its dependencies and type hints
- Examples: Can be created manually or via @asset decorator
- Pattern: Frozen Pydantic model; stores function reference (arbitrary_types_allowed=True); __call__ invokes fn
- Location: `src/lattice/models.py`

**DependencyGraph:**
- Purpose: Immutable bidirectional graph of asset dependencies
- Examples: Adjacency (asset → deps), reverse_adjacency (asset → dependents)
- Pattern: Frozen Pydantic model; built from registry via from_registry(); provides topological_sort() and traversal methods
- Location: `src/lattice/graph.py`

**IOManager:**
- Purpose: Pluggable storage abstraction (load/store/has/delete operations)
- Examples: MemoryIOManager (in-memory dict), FileIOManager (pickle files), ParquetIOManager
- Pattern: ABC with abstract methods; subclasses implement storage logic; LineageIOManager wraps another manager
- Location: `src/lattice/io/base.py` and implementations in `src/lattice/io/`

**ExecutionPlan:**
- Purpose: Ordered, immutable list of assets ready to execute
- Examples: Returned by ExecutionPlan.resolve(); iterable (for asset in plan)
- Pattern: Frozen Pydantic model; stores assets tuple and optional target; resolve() classmethod builds from registry
- Location: `src/lattice/plan.py`

**CheckDefinition & CheckRegistry:**
- Purpose: Define and store data quality checks for assets
- Examples: CheckDefinition(name="count_check", asset_key=..., fn=lambda x: x > 0)
- Pattern: Frozen CheckDefinition; CheckRegistry stores dict[AssetKey] → list[CheckDefinition]
- Location: `src/lattice/observability/checks.py`

**LineageIOManager:**
- Purpose: Wraps another IOManager to track read/write events
- Examples: LineageIOManager(MemoryIOManager()) records all loads/stores to LineageTracker
- Pattern: Composition over inheritance; delegates all calls to wrapped manager while recording events
- Location: `src/lattice/observability/lineage.py`

**RunHistoryStore:**
- Purpose: Persistent storage for run records
- Examples: SQLiteRunHistoryStore (SQLite DB), abstractly extensible to PostgreSQL, etc.
- Pattern: ABC (base.py), SQLite implementation (sqlite.py); stores flat RunRecord structure
- Location: `src/lattice/observability/history/`

## Entry Points

**Library Entry (@asset decorator):**
- Location: User code uses `from lattice import asset`
- Triggers: When Python module loads, decorators register to global registry
- Responsibilities: Asset definition and registration

**Execution Entry (materialize functions):**
- Location: User code calls `lattice.materialize(target=...)` or `materialize_with_observability(...)`
- Triggers: User code invokes the function
- Responsibilities: Load registry, create plan, execute, return result

**CLI Entry (lattice command):**
- Location: `src/lattice/cli.py` main() function (registered in pyproject.toml)
- Triggers: `lattice list`, `lattice show <run_id>`, etc.
- Responsibilities: Parse args, query run history store, format output

**Web Entry (create_app):**
- Location: User code calls `from lattice.web import create_app; app = create_app(registry); uvicorn.run(app)`
- Triggers: Web service startup
- Responsibilities: Build FastAPI app, wire registry and history store, mount routers

## Error Handling

**Strategy:** Explicit exception types for known failures; fail-fast with graceful degradation where appropriate.

**Patterns:**

- **CyclicDependencyError**: Raised during graph construction if a cycle is detected (Kahn's algorithm detects missing nodes). Prevents execution.
- **KeyError**: Raised if target asset not found in registry, or if dependency can't be loaded from IOManager.
- **ValueError**: Raised if asset with same key registered twice, or if explicit_deps parameter is invalid.
- **AssetExecutionError**: Not a built-in, but can be raised by user asset functions; caught, logged, stored in AssetExecutionResult.error.
- **Graceful skipping**: When an asset fails, downstream assets are skipped (not errored), allowing independent branches to continue.
- **Missing import fallback**: ParquetIOManager is optional; if polars not installed, import is caught and __all__ excludes it.

## Cross-Cutting Concerns

**Logging:**
- Approach: Python standard logging module; loggers created via `logging.getLogger(__name__)`
- Configure via: `lattice.configure_logging()` or LATTICE_LOGGING_CONFIG env var
- No output by default (standard logging behavior); users must explicitly enable
- Location: `src/lattice/logging/config.py`

**Validation:**
- Approach: Pydantic BaseModel for all data models (AssetKey, AssetDefinition, ExecutionState, etc.)
- Frozen configs on immutable models (AssetKey, ExecutionResult) to prevent accidental mutation
- Type hints throughout for static analysis (mypy strict mode in pyproject.toml)

**Serialization:**
- Approach: Pydantic models serialize to JSON via model_dump_json(); used for API responses and history storage
- Special handling: AssetDefinition allows arbitrary_types_allowed=True for function reference

**Authentication & Authorization:**
- Approach: Not implemented; web service has no auth layer (assumes local/trusted network)
- For production, wrap create_app() with authentication middleware

**Type Safety:**
- Approach: Full mypy strict mode; TYPE_CHECKING blocks used for circular import avoidance
- Deferred imports: executor imports AssetRegistry only in TYPE_CHECKING to break circular dependency with registry.py

---

*Architecture analysis: 2026-02-06*
