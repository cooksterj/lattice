# Lattice Core Architecture

This document maps how the core Lattice classes and functions interact, covering the full asset lifecycle from definition through execution and observability. The web interface layer is documented separately in [web_architecture.md](web_architecture.md).

---

## Table of Contents

1. [Module Overview](#module-overview)
2. [Asset Definition & Registry](#asset-definition--registry)
3. [Dependency Graph & Execution Planning](#dependency-graph--execution-planning)
4. [Execution Engine](#execution-engine)
5. [IO Manager Abstraction](#io-manager-abstraction)
6. [Observability Stack](#observability-stack)
7. [CLI Interface](#cli-interface)
8. [dbt Integration](#dbt-integration)
9. [Diagrams](#diagrams)

---

## Module Overview

```
src/lattice/
├── __init__.py              # Public API exports
├── asset.py                 # @asset decorator and dependency extraction
├── models.py                # AssetKey, AssetDefinition (Pydantic models)
├── graph.py                 # DependencyGraph with topological sort & cycle detection
├── executor.py              # Executor & AsyncExecutor for materialization
├── plan.py                  # ExecutionPlan resolution
├── registry.py              # AssetRegistry (global + custom)
├── exceptions.py            # CyclicDependencyError
├── cli.py                   # Command-line interface for run history
│
├── io/                      # Asset storage backends
│   ├── base.py              # IOManager ABC
│   ├── memory.py            # In-memory storage
│   ├── file.py              # Filesystem storage (pickle)
│   └── parquet.py           # Parquet file storage (Polars)
│
├── logging/                 # Logging configuration
│   ├── config.py            # configure_logging(), get_logger()
│   └── logging.conf         # Default INI-style log config
│
├── dbt/                    # dbt manifest integration
│   ├── __init__.py          # Public API: dbt_assets, load_dbt_manifest, DBT_GROUP
│   ├── models.py            # DbtModelInfo (Pydantic model)
│   ├── manifest.py          # ManifestParser for manifest.json
│   └── assets.py            # @dbt_assets decorator, load_dbt_manifest, select/deps filtering
│
└── observability/           # Execution monitoring & history
    ├── __init__.py          # materialize_with_observability()
    ├── checks.py            # CheckDefinition, CheckRegistry, AssetWithChecks
    ├── models.py            # CheckResult, LogEntry, LineageEvent, RunResult, RunRecord
    ├── lineage.py           # LineageTracker, LineageIOManager
    ├── log_capture.py       # ExecutionLogHandler, capture_logs()
    └── history/
        ├── base.py          # RunHistoryStore ABC
        └── sqlite.py        # SQLiteRunHistoryStore
```

### Circular Import Avoidance

Several modules use the `TYPE_CHECKING` guard to break circular dependencies at runtime while preserving static type checking:

- `asset.py` imports `AssetWithChecks` from `observability/checks.py` inside `_asset_decorator()` at runtime, but at module level only under `TYPE_CHECKING`.
- `graph.py` imports `AssetRegistry` from `registry.py` only under `TYPE_CHECKING`, using a string annotation `"AssetRegistry"` in method signatures.
- `exceptions.py` imports `AssetKey` from `models.py` only under `TYPE_CHECKING`.
- `executor.py` imports `AssetRegistry` from `registry.py` only under `TYPE_CHECKING`, with a local import inside `AsyncExecutor.execute()`.

---

## Asset Definition & Registry

### AssetKey

`models.py` &mdash; Immutable, hashable identifier for an asset.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Asset name (min 1 char) |
| `group` | `str` | `"default"` | Namespace for organization (min 1 char) |

- `__str__()` returns `"group/name"` when group is not `"default"`, otherwise just `"name"`.
- `__hash__()` hashes `(group, name)`, enabling use as dict keys and in sets.
- Frozen via `ConfigDict(frozen=True)`.

### AssetDefinition

`models.py` &mdash; Metadata wrapper for an asset function.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `AssetKey` | *(required)* | Unique identifier |
| `fn` | `Callable[..., Any]` | *(required)* | The wrapped asset function |
| `dependencies` | `tuple[AssetKey, ...]` | `()` | Assets this asset depends on |
| `return_type` | `Any` | `None` | Return type annotation |
| `description` | `str \| None` | `None` | Human-readable description |

- `__call__()` delegates to `fn`, making the definition callable.
- `__hash__()` hashes by `key`.
- Invariant: at decoration time, `len(dependencies) == len(non-skipped function parameters)` (validated by the `@asset` decorator).

### AssetRegistry

`registry.py` &mdash; Thread-safe container for asset definitions.

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(asset: AssetDefinition) -> None` | Register asset; raises `ValueError` on duplicate key |
| `get` | `(key: AssetKey \| str) -> AssetDefinition` | Retrieve by key; raises `KeyError` if missing |
| `__contains__` | `(key: AssetKey \| str) -> bool` | Membership check |
| `__iter__` | `() -> Iterator[AssetDefinition]` | Iterate all definitions |
| `__len__` | `() -> int` | Count of registered assets |
| `clear` | `() -> None` | Remove all assets |

**Global singleton:** `get_global_registry()` returns a module-level `AssetRegistry`. The `@asset` decorator registers to this by default. Custom registries can be passed via `@asset(registry=my_registry)` for test isolation.

### The `@asset` Decorator

`asset.py` &mdash; Two calling conventions:

```python
# Direct decoration (no arguments)
@asset
def my_asset() -> int: ...

# Parameterized decoration — group shorthand (name derived from function)
@asset(group="analytics", deps=["user_orders"])
def daily_revenue(orders: list[dict]) -> dict: ...

# Parameterized decoration — explicit key (full control)
@asset(key=AssetKey(name="custom", group="analytics"), deps=[...], description="...")
def my_asset(source: dict) -> int: ...
```

The ``group`` parameter is a shorthand for ``key=AssetKey(name=func.__name__, group=group)``. It cannot be combined with ``key``.

**Internal flow** &mdash; see [Decorator Execution Step-by-Step](#decorator-execution-step-by-step) for the full walkthrough:

1. **Validate & resolve key** &mdash; `asset()` validates that `key` and `group` are mutually exclusive (raises `ValueError` if both are provided). When `group` is given, the effective key `AssetKey(name=func.__name__, group=group)` is built at decoration time. `_asset_decorator` receives only a resolved `key` and does not know about `group`.
2. **Normalize dependencies** (`_normalize_deps` + `_extract_dependencies`) &mdash; Convert `deps` list entries (strings become `AssetKey(name=s)`, `AssetKey` objects pass through). If `deps` is `None`, returns empty tuple.
3. **Validate arity** &mdash; Compare `len(dependencies)` against the number of non-skipped parameters (`self`, `cls`, `context`, `partition_key` are skipped). Raises `TypeError` on mismatch.
4. **Extract return type** (`_extract_return_type`) &mdash; Safely read type hints via `get_type_hints()`.
5. **Wrap function** &mdash; `_create_sync_wrapper` or `_create_async_wrapper` (preserves `__name__`, `__doc__`, and async detection via `@wraps`).
6. **Create `AssetDefinition`** with all extracted metadata.
7. **Register** to the target registry.
8. **Return `AssetWithChecks`** wrapping the definition, enabling `.check()` chaining.

### Decorator Execution Step-by-Step

When Python encounters `@asset` on a function definition, the following sequence executes at **import time** (not at materialization time):

#### Step 1: Dispatch — `@asset` vs `@asset(...)`

The `asset()` function uses `@overload` to support two calling conventions. Python resolves this at decoration time:

- **`@asset` (no parentheses):** Python passes the decorated function directly as `fn`. Since `fn is not None`, `_asset_decorator()` is called immediately with the function and default arguments.
- **`@asset(key=..., deps=...)` (with arguments):** Python calls `asset(key=..., deps=...)` first, which validates `key`/`group` mutual exclusion and returns a closure. Python then calls that closure with the decorated function, which resolves the effective key from `group` (if provided) and calls `_asset_decorator()`.

Both paths converge on `_asset_decorator(func, key, deps, description, target_registry)`. The `group` parameter is fully resolved to an `AssetKey` before `_asset_decorator` is called.

#### Step 1.5: Validate & Resolve `group` Shorthand (in `asset()`)

Before `_asset_decorator` is called, the `asset()` function handles the `group` parameter:

```python
# In asset():
if key is not None and group is not None:
    raise ValueError("Cannot specify both 'key' and 'group' ...")

# In the returned closure (when @asset(...) is used):
effective_key = key
if effective_key is None and group is not None:
    effective_key = AssetKey(name=func.__name__, group=group)
# Then: _asset_decorator(func, effective_key, deps, ...)
```

This keeps `_asset_decorator` simple — it only sees a resolved `key` or `None`.

#### Step 2: Resolve the Asset Key (in `_asset_decorator`)

```python
asset_key = key or AssetKey(name=func.__name__)
```

By this point `key` is either an explicit `AssetKey` (from `key=` or resolved from `group=`) or `None`. If `None`, the function's `__name__` attribute becomes the asset name in the `"default"` group. For example, `def daily_revenue()` produces `AssetKey(name="daily_revenue", group="default")`.

#### Step 3: Normalize Dependencies and Validate Arity

Dependencies are declared as a list of `AssetKey` objects or plain strings:

```python
@asset(deps=["raw_users", AssetKey(name="daily_revenue", group="analytics")])
def my_asset(users: list[dict], revenue: dict) -> dict: ...
```

**Normalization (`_normalize_deps`):**

String entries are converted to `AssetKey(name=s)` in the default group. `AssetKey` objects pass through unchanged. If `deps` is `None` (source asset with no dependencies), an empty tuple is returned.

**Arity validation:**

The decorator inspects the function's signature using `_get_asset_params(fn)`, which returns all parameter names excluding the skip set (`self`, `cls`, `context`, `partition_key`). It then validates:

```python
if len(dependencies) != len(params):
    raise TypeError(
        f"Asset '{asset_key}' declares {len(dependencies)} dependency(ies) "
        f"but its function accepts {len(params)} parameter(s). ..."
    )
```

This catches mismatches at import time rather than at execution time.

**Positional injection at execution time:**

The executor derives parameter names from `inspect.signature(asset_def.fn)` at execution time and zips them with `asset_def.dependencies` positionally:

```python
# deps     = [AssetKey("daily_revenue", "analytics"), AssetKey("user_stats", "analytics")]
# params   = ("revenue", "stats")  — derived from inspect.signature at execution time

sig = inspect.signature(asset_def.fn)
param_names = [p for p in sig.parameters if p not in SKIP_PARAMS]
for param_name, dep_key in zip(param_names, asset_def.dependencies, strict=True):
    kwargs[param_name] = io_manager.load(dep_key)
#   kwargs["revenue"]  = io_manager.load(AssetKey("daily_revenue", "analytics"))

asset_def.fn(**kwargs)
# my_asset(revenue=<loaded value>, stats=<loaded value>)
```

This means parameter names are independent of dependency names — the function can use any local variable name, and the positional order in the `deps` list determines which dependency maps to which parameter.

**Example:**

```python
@asset(deps=[
    AssetKey(name="daily_revenue", group="analytics"),
    AssetKey(name="user_stats", group="analytics"),
])
def dashboard(revenue: dict, stats: dict, partition_key: date) -> dict: ...
```

Produces:
- `dependencies = (AssetKey("daily_revenue", "analytics"), AssetKey("user_stats", "analytics"))`
- `partition_key` is skipped (in `SKIP_PARAMS`)
- At execution time: `revenue` receives the loaded value of `daily_revenue`, `stats` receives `user_stats`

#### Step 4: Extract Return Type (`_extract_return_type`)

Calls `typing.get_type_hints(fn)` to read the return annotation. This is wrapped in a `try/except` because `get_type_hints()` can fail on forward references or missing imports. On failure, `None` is returned — the asset proceeds without type information.

#### Step 5: Create Wrapper Function

The decorator detects whether the function is async or sync via `inspect.iscoroutinefunction(func)` and creates the appropriate wrapper:

- **Async functions** → `_create_async_wrapper()` produces an `async def` wrapper that `await`s the original.
- **Sync functions** → `_create_sync_wrapper()` produces a plain `def` wrapper that calls the original.

Both wrappers use `@functools.wraps(func)` to preserve `__name__`, `__doc__`, and `__module__` from the original function. This matters downstream because the executor, logging, and web UI reference `fn.__name__` for display and error messages.

#### Step 6: Build `AssetDefinition`

All extracted metadata is assembled into a frozen Pydantic model:

```python
AssetDefinition(
    key=asset_key,               # From Step 2
    fn=wrapped_fn,               # From Step 5
    dependencies=dependencies,   # From Step 3
    return_type=return_type,     # From Step 4
    description=description or func.__doc__,  # Explicit or docstring
)
```

The invariant `len(dependencies) == len(non-skipped params)` is guaranteed by the arity validation in Step 3.

#### Step 7: Register to Registry

```python
target_registry.register(asset_def)
```

The registry is either the global singleton (from `get_global_registry()`) or a custom registry passed via `@asset(registry=my_registry)`. Registration:

- Raises `ValueError` if an asset with the same key already exists.
- Logs the registration at `INFO` level and the dependency list at `DEBUG` level.

Because this happens at import time, simply importing a module that defines `@asset`-decorated functions causes them to register globally.

#### Step 8: Return `AssetWithChecks`

```python
return AssetWithChecks(asset_def)
```

The decorator replaces the original function with an `AssetWithChecks` wrapper. This wrapper:

- Delegates all attribute access (`key`, `fn`, `dependencies`, etc.) to the underlying `AssetDefinition`.
- Exposes a `.check()` method for attaching data quality checks (see [AssetWithChecks](#assetwithchecks) below).
- Is callable — `my_asset()` invokes `asset_def.fn()` — so the function remains usable outside the framework.

### AssetWithChecks

`observability/checks.py` &mdash; Wrapper returned by `@asset` that enables the `.check()` decorator API.

```python
@my_asset.check
def value_positive(data: dict) -> bool:
    return data["value"] > 0

@my_asset.check(name="custom_name", description="Validates value range")
def value_in_range(data: dict) -> bool:
    return 0 < data["value"] < 100
```

- Delegates all attribute access (`key`, `fn`, `dependencies`, etc.) to the underlying `AssetDefinition`.
- `.check()` creates a `CheckDefinition` and registers it to the `CheckRegistry`.
- Returns the original check function unchanged (supports stacking multiple checks).

---

## Dependency Graph & Execution Planning

### DependencyGraph

`graph.py` &mdash; Immutable graph of asset dependencies with traversal operations.

| Field | Type | Description |
|-------|------|-------------|
| `adjacency` | `dict[AssetKey, tuple[AssetKey, ...]]` | Forward edges: asset -> its dependencies |
| `reverse_adjacency` | `dict[AssetKey, tuple[AssetKey, ...]]` | Reverse edges: asset -> its dependents |

**Construction:**

```python
graph = DependencyGraph.from_registry(registry)
```

`from_registry()` iterates all registered assets, builds both adjacency maps in O(V+E) time, and returns a frozen instance.

**Cycle Detection** (`detect_cycles`) &mdash; DFS three-color algorithm:

| Color | Value | Meaning |
|-------|-------|---------|
| WHITE | 0 | Not yet visited |
| GRAY | 1 | On current recursion stack |
| BLACK | 2 | Fully explored |

The helper `_dfs_cycle_detect()` walks the graph. A back-edge (edge to a GRAY node) indicates a cycle. The cycle path is reconstructed by walking the parent chain. External dependencies (not in the graph) are skipped. Returns `list[list[AssetKey]]` of cycles or `None`.

**Topological Sort** (`topological_sort`) &mdash; Kahn's algorithm:

1. Compute in-degree for each node (count of internal dependencies).
2. Enqueue all nodes with in-degree 0 (source assets).
3. Dequeue a node, append to result, decrement in-degree of all dependents.
4. When a dependent reaches in-degree 0, enqueue it.
5. If result length != node count, a cycle exists &mdash; raises `CyclicDependencyError`.

**Traversal methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `get_all_upstream(key)` | `set[AssetKey]` | All transitive dependencies (iterative DFS on `adjacency`) |
| `get_all_downstream(key)` | `set[AssetKey]` | All transitive dependents (iterative DFS on `reverse_adjacency`) |
| `get_execution_levels(keys?)` | `list[list[AssetKey]]` | Groups assets by depth for parallel execution |

`get_execution_levels()` uses a memoized recursive helper `_compute_level()`:
- Level 0: assets with no in-subset dependencies.
- Level N: `max(dependency levels) + 1`.
- Assets within the same level are independent and can execute in parallel.

### CyclicDependencyError

`exceptions.py` &mdash; Raised when a cycle is detected.

- Stores `cycle: list[AssetKey]` with the repeated node at both start and end.
- Message format: `"Cyclic dependency detected: A -> B -> C -> A"`.

### ExecutionPlan

`plan.py` &mdash; An ordered, immutable plan for materializing assets.

| Field | Type | Description |
|-------|------|-------------|
| `assets` | `tuple[AssetDefinition, ...]` | Assets in topological order |
| `target` | `AssetKey \| None` | Target asset if subset was resolved |

**Resolution:**

```python
plan = ExecutionPlan.resolve(registry, target="model", include_downstream=False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `registry` | `AssetRegistry` | *(required)* | Source of asset definitions |
| `target` | `AssetKey \| str \| None` | `None` | Target asset (string parsed as `"group/name"` or `"name"`) |
| `include_downstream` | `bool` | `False` | Resolution mode |

**Two resolution modes:**

| Mode | include_downstream | Includes | Use Case |
|------|-------------------|----------|----------|
| Upstream (default) | `False` | Target + all transitive dependencies | Run a specific asset with everything it needs |
| Downstream | `True` | Target + all transitive dependents | Re-execute a failed asset and refresh everything downstream |

Resolution flow: build graph -> topological sort -> filter to required set -> convert keys to definitions -> return frozen plan.

**Protocol methods:** `__iter__` (yields assets in order), `__len__` (asset count), `__contains__` (membership by key or string).

---

## Execution Engine

### AssetStatus

`executor.py` &mdash; String enum for asset execution state.

| Value | Description |
|-------|-------------|
| `PENDING` | Not yet started |
| `RUNNING` | Currently executing |
| `COMPLETED` | Finished successfully |
| `FAILED` | Raised an exception |
| `SKIPPED` | Skipped due to upstream failure or cancellation |

### ExecutionState (Mutable)

Tracks real-time progress during execution. Exposed via `executor.current_state`.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | 8-char UUID prefix |
| `started_at` | `datetime` | Run start time |
| `completed_at` | `datetime \| None` | Run end time |
| `status` | `AssetStatus` | Overall status |
| `current_asset` | `AssetKey \| None` | Currently executing asset |
| `asset_results` | `dict[str, AssetExecutionResult]` | Results keyed by string repr |
| `total_assets` | `int` | Total in plan |
| `completed_count` | `int` | Successes |
| `failed_count` | `int` | Failures |

### AssetExecutionResult (Immutable)

Result of executing a single asset.

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AssetKey` | The executed asset |
| `status` | `AssetStatus` | Final status |
| `started_at` | `datetime \| None` | Start time (None if skipped) |
| `completed_at` | `datetime \| None` | End time (None if skipped) |
| `duration_ms` | `float \| None` | Duration (None if skipped) |
| `error` | `str \| None` | Error message if failed |

### ExecutionResult (Immutable)

Final summary of a complete execution run.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Unique run identifier |
| `started_at` | `datetime` | Run start |
| `completed_at` | `datetime` | Run end |
| `status` | `AssetStatus` | `COMPLETED` or `FAILED` |
| `asset_results` | `tuple[AssetExecutionResult, ...]` | Per-asset results in order |
| `total_assets` | `int` | Total in plan |
| `completed_count` | `int` | Successes |
| `failed_count` | `int` | Failures |
| `duration_ms` | `float` | Total duration |

### Executor (Synchronous)

```python
Executor(
    io_manager: IOManager | None = None,        # Defaults to MemoryIOManager
    on_asset_start: Callable[[AssetKey], None] | None = None,
    on_asset_complete: Callable[[AssetExecutionResult], None] | None = None,
    partition_key: date | None = None,
)
```

**`execute(plan: ExecutionPlan) -> ExecutionResult`:**

1. Generate `run_id`, create `ExecutionState`.
2. Iterate assets in plan order.
3. For each asset, call `_execute_asset()`:
   - Derive parameter names from `inspect.signature(asset_def.fn)`, excluding `SKIP_PARAMS`.
   - Load dependencies via `io_manager.load(dep_key)` for each `(param_name, dep_key)` pair (positional zip).
   - Inject `partition_key` if the function accepts it (checked via `inspect.signature`).
   - Invoke `asset_def.fn(**kwargs)`.
   - Store result via `io_manager.store(key, result_value)`.
   - On success: return `AssetExecutionResult` with `COMPLETED`.
   - On exception: catch, return `AssetExecutionResult` with `FAILED` and error string.
4. **Failure propagation:** After the first failure, all remaining assets are marked `SKIPPED`.
5. Fire `on_asset_start` / `on_asset_complete` callbacks.
6. Build and return `ExecutionResult`.
7. Clear `current_state` in `finally` block.

### AsyncExecutor (Parallel)

```python
AsyncExecutor(
    io_manager: IOManager | None = None,
    max_concurrency: int = 4,                   # Semaphore limit
    on_asset_start: Callable[[AssetKey], Any] | None = None,   # Sync or async
    on_asset_complete: Callable[[AssetExecutionResult], Any] | None = None,
    partition_key: date | None = None,
)
```

**`async execute(plan: ExecutionPlan) -> ExecutionResult`:**

Key differences from sync `Executor`:

1. **Level-based parallelism** &mdash; Builds a temporary `DependencyGraph` from the plan, calls `get_execution_levels()` to group independent assets.
2. **Semaphore concurrency** &mdash; `asyncio.Semaphore(max_concurrency)` limits parallel tasks across all levels.
3. **TaskGroup execution** &mdash; Each level's runnable assets are launched via `asyncio.TaskGroup`, running concurrently within the semaphore limit.
4. **Async/sync function support** &mdash; Detects via `inspect.iscoroutinefunction()`. Sync functions run via `asyncio.to_thread()` to avoid blocking.
5. **Async callbacks** &mdash; Callbacks can be sync or async; result is checked with `inspect.iscoroutine()` and awaited if needed.
6. **Cancellation** &mdash; `cancel()` sets a flag; running assets complete but no new ones start.
7. **Skip propagation** &mdash; Assets whose dependencies are in `failed_keys` are skipped before level execution.

### Convenience Functions

```python
def materialize(
    registry: AssetRegistry | None = None,   # Defaults to global
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
) -> ExecutionResult

async def materialize_async(
    registry: AssetRegistry | None = None,
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
    max_concurrency: int = 4,
) -> ExecutionResult
```

Both resolve an `ExecutionPlan`, create the appropriate executor, and return `ExecutionResult`.

---

## IO Manager Abstraction

### IOManager ABC

`io/base.py` &mdash; Abstract interface for asset storage backends.

| Method | Signature | Required | Description |
|--------|-----------|----------|-------------|
| `load` | `(key: AssetKey, annotation: type[T] \| None = None) -> T` | Yes | Load asset value; raises `KeyError` if missing |
| `store` | `(key: AssetKey, value: Any) -> None` | Yes | Persist asset value (last-write-wins) |
| `has` | `(key: AssetKey) -> bool` | Yes | Check existence without loading |
| `delete` | `(key: AssetKey) -> None` | No | Remove asset; default raises `NotImplementedError` |

### MemoryIOManager

`io/memory.py` &mdash; In-memory volatile storage.

- Storage: `dict[AssetKey, Any]` &mdash; objects stored as-is, no serialization.
- Additional methods: `clear()`, `__len__()`, `__contains__()`.
- O(1) operations. Ephemeral &mdash; data lost on process exit.
- Default IO manager when none is provided to executors.

### FileIOManager

`io/file.py` &mdash; Persistent filesystem storage using Python pickle.

- Constructor: `FileIOManager(base_path: Path | str)` &mdash; creates directory hierarchy.
- Path layout: `{base_path}/{group}/{name}.pkl`.
- Serialization: `pickle.dump()` / `pickle.load()` in binary mode.
- Group directories created lazily on first store.

### ParquetIOManager

`io/parquet.py` &mdash; Specialized storage for Polars DataFrames.

- Constructor: `ParquetIOManager(base_path: Path | str)`.
- Path layout: `{base_path}/{group}/{name}.parquet`.
- `store()` validates `isinstance(value, pl.DataFrame)`, raises `TypeError` otherwise.
- Polars imported lazily (only when methods are called), allowing graceful degradation if not installed.
- Efficient columnar compression, cross-language compatible format.

### Comparison

| Feature | MemoryIOManager | FileIOManager | ParquetIOManager |
|---------|-----------------|---------------|------------------|
| Persistence | Ephemeral | Persistent | Persistent |
| Serialization | None | Pickle | Apache Parquet |
| Data types | Any Python object | Any pickleable object | Polars DataFrames only |
| Performance | O(1) memory ops | Disk I/O bound | Fast columnar ops |
| `delete()` | Supported | Supported | Supported |

### Executor Integration

The executor uses IOManager in a **load-execute-store** cycle. Parameter names are derived from `inspect.signature(asset_def.fn)` at execution time and zipped positionally with `asset_def.dependencies`:

```python
# 1. Derive parameter names from function signature
sig = inspect.signature(asset_def.fn)
param_names = [p for p in sig.parameters if p not in SKIP_PARAMS]

# 2. Load each dependency
for param_name, dep_key in zip(param_names, asset_def.dependencies, strict=True):
    kwargs[param_name] = self.io_manager.load(dep_key)

# 3. Execute asset function
result_value = asset_def.fn(**kwargs)

# 4. Store result
self.io_manager.store(key, result_value)
```

---

## Observability Stack

### Data Quality Checks

**CheckDefinition** (`observability/checks.py`) &mdash; Frozen model defining a check.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Check name |
| `asset_key` | `AssetKey` | Target asset |
| `fn` | `Callable[..., CheckResult \| bool]` | Check function |
| `description` | `str \| None` | Optional description |

**CheckRegistry** &mdash; Mutable registry storing checks by asset key.

| Method | Description |
|--------|-------------|
| `register(check)` | Register a CheckDefinition |
| `get_checks(key)` | Get all checks for an asset (returns copy) |
| `all_checks()` | Get all checks across all assets |
| `clear()` | Remove all checks |

Global singleton via `get_global_check_registry()`.

**`run_check(check_def, value) -> CheckResult`** &mdash; Executes a check function:
- If it returns `bool`: wraps in `CheckResult` with `PASSED`/`FAILED`.
- If it returns `CheckResult`: returns as-is.
- If it raises: returns `CheckResult` with `ERROR` status and error message.
- Always records `duration_ms`.

**CheckStatus** enum: `PASSED`, `FAILED`, `SKIPPED`, `ERROR`.

**CheckResult** &mdash; Frozen model with fields: `passed`, `check_name`, `asset_key`, `status`, `metadata`, `duration_ms`, `error`.

### Log Capture

**ExecutionLogHandler** (`observability/log_capture.py`) &mdash; A `logging.Handler` subclass that captures log entries during execution.

- `set_current_asset(key)` &mdash; Sets the asset context so captured logs are tagged.
- `emit(record)` &mdash; Creates a `LogEntry` from the `LogRecord`, appends to internal list, fires optional `on_entry` callback.

**`capture_logs(logger_name="lattice", level=DEBUG, on_entry=None)`** &mdash; Context manager that temporarily attaches an `ExecutionLogHandler` to a logger and yields it.

**LogEntry** &mdash; Frozen model: `timestamp`, `level`, `logger_name`, `message`, `asset_key`.

### Lineage Tracking

**LineageTracker** (`observability/lineage.py`) &mdash; Records read/write events during execution.

- `set_current_asset(key)` &mdash; Sets the source asset context.
- `record_read(key, metadata?)` &mdash; Creates a `LineageEvent(event_type="read", ...)`.
- `record_write(key, metadata?)` &mdash; Creates a `LineageEvent(event_type="write", ...)`.
- `events` property returns a copy of the event list.

**LineageIOManager** &mdash; Wraps any `IOManager` to transparently record lineage:
- `load()` &mdash; records a read event, then delegates.
- `store()` &mdash; delegates, then records a write event.
- `has()` / `delete()` &mdash; direct delegation, no tracking.

**LineageEvent** &mdash; Frozen model: `event_type` (`"read"` | `"write"`), `asset_key`, `timestamp`, `source_asset`, `metadata`.

### Run History

**RunResult** (`observability/models.py`) &mdash; Frozen model combining execution result with observability data.

| Field | Type | Description |
|-------|------|-------------|
| `execution_result` | `ExecutionResult` | Core execution data |
| `logs` | `tuple[LogEntry, ...]` | Captured log entries |
| `lineage` | `tuple[LineageEvent, ...]` | Read/write events |
| `check_results` | `tuple[CheckResult, ...]` | Data quality check results |

Properties: `run_id`, `status`, `success`.

**RunRecord** &mdash; Flat frozen model for SQLite persistence. Complex data stored as JSON strings.

- `from_run_result(result, target?, partition_key?)` &mdash; Serializes logs, lineage, checks, and asset results to JSON.

**RunHistoryStore ABC** (`observability/history/base.py`):

| Method | Signature | Description |
|--------|-----------|-------------|
| `save` | `(record: RunRecord) -> None` | Persist a run record |
| `get` | `(run_id: str) -> RunRecord \| None` | Retrieve by ID |
| `list_runs` | `(limit=50, status=None, offset=0) -> list[RunRecord]` | List records (newest first) |
| `delete` | `(run_id: str) -> bool` | Delete by ID |
| `count` | `(status=None) -> int` | Count records |
| `clear` | `() -> int` | Delete all records |

**SQLiteRunHistoryStore** (`observability/history/sqlite.py`):

- Constructor: `SQLiteRunHistoryStore(db_path="lattice_runs.db")` &mdash; accepts `":memory:"` for testing.
- Schema: `runs` table with columns matching `RunRecord` fields, indexed on `started_at DESC`.
- Connection management: persistent connection for in-memory, per-operation for file-based.
- Overrides `count()` and `clear()` with optimized SQL queries.

### `materialize_with_observability()`

`observability/__init__.py` &mdash; The orchestration function that wires all observability components together.

```python
def materialize_with_observability(
    registry: AssetRegistry | None = None,
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
    history_store: RunHistoryStore | None = None,
    check_registry: CheckRegistry | None = None,
    partition_key: date | None = None,
) -> RunResult
```

**Execution flow:**

1. **Setup** &mdash; Default to global registries. Create `LineageTracker`. Wrap `io_manager` with `LineageIOManager`.
2. **Plan** &mdash; `ExecutionPlan.resolve(registry, target)`.
3. **Callbacks** &mdash; Define `on_asset_start` that updates both `LineageTracker` and `ExecutionLogHandler` with current asset context.
4. **Execute** &mdash; Within a `capture_logs()` context manager, run `Executor.execute(plan)`.
5. **Check** &mdash; For each completed asset, load its value from the base IO manager, run all registered checks via `run_check()`.
6. **Build** &mdash; Construct `RunResult` with execution result, logs, lineage, and check results.
7. **Persist** &mdash; If `history_store` is provided, convert to `RunRecord` and save.
8. **Return** &mdash; `RunResult`.

---

## CLI Interface

`cli.py` &mdash; Command-line tool for managing run history.

**Global option:** `--db <path>` (default: `lattice_runs.db`)

| Command | Description |
|---------|-------------|
| `lattice list [--limit N] [--status STATUS]` | List recent runs |
| `lattice show <run_id> [--logs] [--checks] [--lineage] [--assets] [--all]` | Show run details |
| `lattice delete <run_id>` | Delete a run record |
| `lattice clear [--force]` | Clear all run records |

Output includes status icons, duration, asset counts, and optional sections for logs, check results, lineage events, and asset results.

---

## dbt Integration

The `dbt/` module reads a dbt `manifest.json` and registers each model as a standard `AssetDefinition` in the Lattice `AssetRegistry` with `group="dbt"`. This allows dbt models to appear alongside native Lattice assets in the DAG graph, with inter-model dependencies preserved as Lattice dependency edges.

dbt tests are intentionally not mapped to Lattice checks — dbt handles its own testing via `dbt test` and `.yml` schema tests.

### DbtModelInfo

`dbt/models.py` &mdash; Frozen Pydantic model representing a single dbt model extracted from the manifest.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `unique_id` | `str` | *(required)* | dbt unique identifier (e.g., `"model.project.model_name"`) |
| `name` | `str` | *(required)* | Model name |
| `description` | `str \| None` | `None` | Optional model description |
| `materialization` | `str` | `"table"` | Materialization strategy (table, view, incremental) |
| `schema_name` | `str \| None` | `None` | Target schema |
| `database` | `str \| None` | `None` | Target database |
| `depends_on` | `tuple[str, ...]` | `()` | Unique IDs of upstream model dependencies |
| `tags` | `tuple[str, ...]` | `()` | Tags associated with this model |

### ManifestParser

`dbt/manifest.py` &mdash; Reads a dbt `manifest.json` and extracts model nodes.

```python
models = ManifestParser.parse("path/to/manifest.json")
```

**Parsing flow:**
1. Read and validate JSON structure.
2. Iterate `nodes` — filter to `resource_type == "model"`.
3. For each model node, extract materialization from `config.materialized`, filter `depends_on.nodes` to model-only refs (prefix `"model."`), and collect `tags`.
4. Return `list[DbtModelInfo]`.

Non-model resource types (sources, seeds, tests, snapshots) are skipped.

### `load_dbt_manifest()`

`dbt/assets.py` &mdash; The main function that parses a manifest and registers dbt models as Lattice assets.

```python
def load_dbt_manifest(
    manifest_path: str | Path | None = None,
    *,
    project_dir: str | Path | None = None,
    select: str | None = None,
    deps: list[AssetDefinition] | None = None,
    registry: AssetRegistry | None = None,
) -> list[AssetDefinition]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `manifest_path` | `str \| Path \| None` | `None` | Path to manifest.json |
| `project_dir` | `str \| Path \| None` | `None` | dbt project directory (runs `dbt parse` automatically) |
| `select` | `str \| None` | `None` | Tag filter expression (e.g., `"tag:silver"`) |
| `deps` | `list[AssetDefinition] \| None` | `None` | Upstream assets for group-level dependencies |
| `registry` | `AssetRegistry \| None` | `None` | Target registry (defaults to global) |

Exactly one of `manifest_path` or `project_dir` must be provided. When `project_dir` is given, `dbt parse --no-partial-parse` is executed first and the resulting `target/manifest.json` is loaded.

**Registration flow:**

1. Parse manifest into `list[DbtModelInfo]` via `ManifestParser.parse()`.
2. Build `model_map` from *all* parsed models (enables cross-filter dependency resolution).
3. Apply `select` filter if provided (only the filtered subset is registered).
4. For each model in the filtered set:
   - Build `AssetKey(name=model.name, group="dbt")`.
   - Resolve manifest-level dependencies via `model_map` (dependencies outside the manifest are silently dropped).
   - Merge `deps` keys (deduplicated with `dict.fromkeys` to avoid duplicates when the manifest already declares the same edge).
   - Create a stub function with matching parameter count (see [Stub Functions](#stub-functions)).
   - Register `AssetDefinition` with metadata (`source`, `materialization`, `schema`, `database`, `dbt_unique_id`, `tags`).

### `@dbt_assets` Decorator

`dbt/assets.py` &mdash; Decorator wrapping `load_dbt_manifest()` for declarative usage.

```python
@dbt_assets(manifest="path/to/manifest.json")
def jaffle_shop(assets):
    '''All models from the manifest.'''

@dbt_assets(manifest="path/to/manifest.json", select="tag:core")
def core_models(assets):
    '''Only core-tagged models.'''

@dbt_assets(manifest="path/to/manifest.json", select="tag:core_final", deps=[core_models])
def final_models(assets):
    '''Final layer — every model depends on all core models.'''
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `manifest` | `str \| Path \| None` | `None` | Path to manifest.json |
| `project_dir` | `str \| Path \| None` | `None` | dbt project directory |
| `select` | `str \| None` | `None` | Tag filter expression |
| `deps` | `list[Callable] \| None` | `None` | Previously `@dbt_assets`-decorated functions |
| `registry` | `AssetRegistry \| None` | `None` | Target registry (defaults to global) |

**Decorator behavior:**

1. If `deps` is provided, extract `_dbt_assets` from each referenced function (raises `TypeError` if the function was not decorated with `@dbt_assets`).
2. Call `load_dbt_manifest()` with all parameters.
3. Store the returned asset list on the decorated function as `fn._dbt_assets` (enabling it to be referenced by downstream `deps`).
4. Call `fn(assets)` once at decoration time.
5. Return the original function unchanged.

### Select & Tag Filtering

The `select` parameter accepts dbt-style `tag:<value>` expressions to register only a subset of models from the manifest.

**`_parse_select(select)`** splits on `:` and validates:
- Must have format `tag:<value>` (no bare words, no empty values).
- Only `tag` is supported as a selector type; other prefixes raise `ValueError`.

**`_filter_models(models, select)`** applies the parsed expression:
- For `tag`: returns only models where `value in model.tags`.

**Cross-filter dependency resolution:** The `model_map` used for dependency resolution is built from *all* parsed models, not the filtered subset. This means a filtered model can still resolve dependencies on models outside its filter — critical for multi-decorator patterns where `tag:core_final` models depend on `tag:core` models declared by a separate decorator.

### Group-Level Dependencies (`deps`)

The `deps` parameter creates explicit dependency edges between groups of models registered by separate decorator calls. Every model registered by the current call receives additional dependency edges pointing to all assets in the `deps` list.

```
@dbt_assets(select="tag:core")          # Registers models A, B
def core(assets): ...

@dbt_assets(select="tag:final", deps=[core])  # Registers model C
def final(assets): ...
# C now depends on A and B (plus any manifest-level deps)
```

Dependency keys from `deps` are merged with manifest-level dependencies and deduplicated, so if the manifest already declares `C -> A`, the edge is not duplicated.

### Stub Functions

Each dbt model is registered with a generated stub function that satisfies the `AssetDefinition.fn` contract (parameter count must match dependency count). Stubs are generated via `exec()` with named parameters (`dep_0`, `dep_1`, ...) because `inspect.signature` on `*args` functions would break the executor's strict positional zip.

Stubs return a metadata dict (`dbt_model`, `materialization`, `schema`, `database`) but are not intended to be invoked during real pipeline runs — dbt models are materialized by `dbt build`, not by Lattice's executor.

---

## Diagrams

### Module Dependency Diagram

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4a5568', 'lineColor': '#a0aec0', 'fontSize': '13px'}}}%%
flowchart LR
    classDef core fill:#4a6fa5,stroke:#345080,color:#f0f0f0,rx:8,ry:8
    classDef io fill:#7b6b8a,stroke:#5a4d6b,color:#f0f0f0,rx:8,ry:8
    classDef obs fill:#5a8a72,stroke:#3d6b52,color:#f0f0f0,rx:8,ry:8
    classDef tool fill:#a0885a,stroke:#7a6840,color:#f0f0f0,rx:8,ry:8
    classDef dbt fill:#5a7a8a,stroke:#3d5a6b,color:#f0f0f0,rx:8,ry:8

    subgraph CORE [" Core "]
        direction TB
        asset_mod(["asset.py"]):::core
        registry_mod(["registry.py"]):::core
        models_mod(["models.py"]):::core
        dep_graph(["graph.py"]):::core
        plan_mod(["plan.py"]):::core
        executor_mod(["executor.py"]):::core

        asset_mod --> registry_mod --> models_mod
        dep_graph --> models_mod
        plan_mod --> dep_graph
        plan_mod --> registry_mod
        executor_mod --> plan_mod
    end

    subgraph IOMGR [" IO Managers "]
        direction TB
        io_base(["IOManager ABC"]):::io
        io_memory(["MemoryIOManager"]):::io
        io_file(["FileIOManager"]):::io
        io_parquet(["ParquetIOManager"]):::io

        io_memory --> io_base
        io_file --> io_base
        io_parquet --> io_base
    end

    subgraph OBS [" Observability "]
        direction TB
        obs_init(["materialize_with_observability"]):::obs
        checks_mod(["checks.py"]):::obs
        lineage_mod(["lineage.py"]):::obs
        log_capture_mod(["log_capture.py"]):::obs
        obs_models_mod(["models.py"]):::obs
        history_mod(["history/sqlite.py"]):::obs

        obs_init --> checks_mod
        obs_init --> lineage_mod
        obs_init --> log_capture_mod
        obs_init --> history_mod
        log_capture_mod --> obs_models_mod
        history_mod --> obs_models_mod
    end

    subgraph DBT [" dbt Integration "]
        direction TB
        dbt_assets_mod(["assets.py"]):::dbt
        dbt_manifest_mod(["manifest.py"]):::dbt
        dbt_models_mod(["models.py"]):::dbt

        dbt_assets_mod --> dbt_manifest_mod --> dbt_models_mod
    end

    cli_mod(["cli.py"]):::tool

    %% Cross-group edges
    executor_mod ==> io_base
    asset_mod -.->|"runtime import"| checks_mod
    obs_init ==> executor_mod
    obs_init ==> plan_mod
    lineage_mod --> io_base
    obs_models_mod --> executor_mod
    cli_mod --> history_mod
    dbt_assets_mod --> registry_mod
    dbt_assets_mod --> models_mod
```

### Materialization Lifecycle

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4a5568', 'lineColor': '#a0aec0', 'fontSize': '13px'}}}%%
flowchart TD
    classDef phase fill:#4a6fa5,stroke:#345080,color:#f0f0f0,rx:8,ry:8
    classDef decision fill:#a0885a,stroke:#7a6840,color:#f0f0f0
    classDef success fill:#5a8a72,stroke:#3d6b52,color:#f0f0f0,rx:8,ry:8
    classDef fail fill:#a05a5a,stroke:#7a3d3d,color:#f0f0f0,rx:8,ry:8
    classDef result fill:#7b6b8a,stroke:#5a4d6b,color:#f0f0f0,rx:8,ry:8

    A(["@asset decorator"]):::phase
    B(["AssetDefinition"]):::phase
    C(["AssetRegistry"]):::phase
    D(["DependencyGraph"]):::phase
    E{"Cycle detected?"}:::decision
    F(["CyclicDependencyError"]):::fail
    G(["ExecutionPlan"]):::phase

    A -->|"extract deps & wrap fn"| B
    B -->|"register()"| C
    C -->|"from_registry()"| D
    D -->|"topological_sort()"| E
    E -- Yes --> F
    E -- No --> G

    subgraph EXEC [" Executor Loop "]
        direction TB
        H(["Load deps via IOManager"]):::phase
        I(["Inject partition_key"]):::phase
        J(["Invoke fn(**kwargs)"]):::phase
        K{"Success?"}:::decision
        L(["store() result"]):::success
        M(["Mark FAILED — skip downstream"]):::fail
    end

    G -->|"iterate plan"| H
    H --> I --> J --> K
    K -- Yes --> L
    K -- No --> M

    N(["ExecutionResult"]):::result
    L --> N
    M --> N
```

### Observability Orchestration

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorLineColor': '#a0aec0', 'signalColor': '#4a6fa5', 'noteBkgColor': '#e8e8e0', 'noteTextColor': '#2d3748', 'activationBorderColor': '#4a6fa5', 'fontSize': '13px'}}}%%
sequenceDiagram
    actor User
    participant MWO as materialize_with_<br/>observability()
    participant LT as Lineage<br/>Tracker
    participant LIO as Lineage<br/>IOManager
    participant LC as Log<br/>Capture
    participant EX as Executor
    participant IO as IOManager
    participant CR as Check<br/>Registry

    User ->> MWO: call(registry, target, io_manager)

    rect rgba(74, 111, 165, 0.1)
        Note right of MWO: Setup phase
        MWO ->> LT: create()
        MWO ->> LIO: wrap(io_manager)
        MWO ->> LC: enter context
    end

    rect rgba(90, 138, 114, 0.1)
        Note right of MWO: Execution phase
        loop Each asset in plan
            EX -->> MWO: on_asset_start(key)
            MWO ->> LT: set_current_asset(key)
            MWO ->> LC: set_current_asset(key)

            EX ->> LIO: load(dep_key)
            LIO ->> LT: record_read
            LIO ->> IO: load(dep_key)
            IO -->> EX: value

            Note over EX: invoke fn(**kwargs)

            EX ->> LIO: store(key, result)
            LIO ->> IO: store(key, result)
            LIO ->> LT: record_write
        end
    end

    rect rgba(160, 136, 90, 0.1)
        Note right of MWO: Checks phase
        loop Each completed asset
            MWO ->> CR: get_checks(key)
            MWO ->> IO: load(key)
            Note over MWO: run_check(def, value)
        end
    end

    rect rgba(123, 107, 138, 0.1)
        Note right of MWO: Persist phase
        MWO ->> MWO: build RunResult
        opt history_store provided
            MWO ->> MWO: save RunRecord
        end
    end

    MWO -->> User: RunResult
```

### AsyncExecutor Level-Based Parallelism

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#a0aec0', 'fontSize': '13px'}}}%%
flowchart LR
    classDef lv0 fill:#4a6fa5,stroke:#345080,color:#f0f0f0,rx:8,ry:8
    classDef lv1 fill:#7b6b8a,stroke:#5a4d6b,color:#f0f0f0,rx:8,ry:8
    classDef lv2 fill:#5a8a72,stroke:#3d6b52,color:#f0f0f0,rx:8,ry:8
    classDef sem fill:#a0885a,stroke:#7a6840,color:#f0f0f0,rx:4,ry:4

    SEM["Semaphore\nmax_concurrency = 4"]:::sem

    subgraph L0 [" Level 0 — parallel "]
        A(["Asset A"]):::lv0
        B(["Asset B"]):::lv0
    end

    subgraph L1 [" Level 1 — parallel "]
        C(["Asset C"]):::lv1
        D(["Asset D"]):::lv1
    end

    subgraph L2 [" Level 2 "]
        E(["Asset E"]):::lv2
    end

    A --> C
    A --> D
    B --> D
    C --> E
    D --> E

    SEM ~~~ L0
```

Assets within the same level execute concurrently (up to `max_concurrency`). All assets in a level must complete before the next level begins. A failure in any asset causes its downstream dependents to be skipped.

### dbt Registration & Filtering

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4a5568', 'lineColor': '#a0aec0', 'fontSize': '13px'}}}%%
flowchart TD
    classDef phase fill:#5a7a8a,stroke:#3d5a6b,color:#f0f0f0,rx:8,ry:8
    classDef decision fill:#a0885a,stroke:#7a6840,color:#f0f0f0
    classDef result fill:#5a8a72,stroke:#3d6b52,color:#f0f0f0,rx:8,ry:8
    classDef core fill:#4a6fa5,stroke:#345080,color:#f0f0f0,rx:8,ry:8

    A(["@dbt_assets decorator"]):::phase
    B(["ManifestParser.parse()"]):::phase
    C(["All models + full model_map"]):::phase
    D{"select provided?"}:::decision
    E(["_filter_models(tag:value)"]):::phase
    F(["Filtered model subset"]):::phase
    G{"deps provided?"}:::decision
    H(["Extract _dbt_assets from dep fns"]):::phase
    I(["Merge extra_dep_keys"]):::phase

    A -->|"manifest or project_dir"| B
    B --> C
    C --> D
    D -- Yes --> E --> F
    D -- No --> F
    F --> G
    G -- Yes --> H --> I
    G -- No --> I

    subgraph REG [" Per-model registration "]
        direction TB
        J(["_build_dependency_keys\n(resolves against full model_map)"]):::phase
        K(["Deduplicate: manifest deps + extra deps"]):::phase
        L(["_create_stub_fn(dep_count)"]):::phase
        M(["AssetDefinition + metadata"]):::core
        N(["registry.register()"]):::result
    end

    I --> J --> K --> L --> M --> N
    N -->|"Store on fn._dbt_assets"| A
```

This diagram shows how `select` filtering and `deps` merging interact. The `model_map` is always built from all parsed models so that dependency resolution works across filter boundaries. The `deps` keys are deduplicated with manifest-level dependencies via `dict.fromkeys` to prevent duplicate edges when the manifest already declares the same dependency.
