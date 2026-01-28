# Lattice

An asset-centric orchestration framework inspired by Dagster's design philosophy.

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

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

## Overview

Lattice is a learning project to build a lightweight orchestration system with core concepts: assets, dependency resolution, materialization, and lineage tracking. The goal is to gain deep familiarity with complex Python patterns, async programming, and AWS deployment.

```
┌─────────────────────────────────────────────────────────┐
│                       Lattice                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  Registry   │  │  Resolver   │  │  Executor       │  │
│  │  (assets)   │──│  (DAG)      │──│  (run assets)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│         │                                    │          │
│  ┌──────▼──────┐              ┌──────────────▼───────┐  │
│  │  @asset     │              │  IO Managers         │  │
│  │  decorator  │              │  (load/store)        │  │
│  └─────────────┘              └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1: The `@asset` Decorator & Registry

**Goal:** Declarative asset definitions with automatic dependency detection.

```python
from lattice import asset, AssetKey

@asset
def raw_users() -> pd.DataFrame:
    """No dependencies - source asset."""
    return pd.read_csv("users.csv")

@asset
def cleaned_users(raw_users: pd.DataFrame) -> pd.DataFrame:
    """Depends on raw_users (inferred from signature)."""
    return raw_users.dropna()

@asset(key=AssetKey("analytics", "user_stats"))
def user_statistics(cleaned_users: pd.DataFrame) -> dict:
    """Namespaced asset key."""
    return {"count": len(cleaned_users)}
```

**Python patterns:**
- Decorators with optional arguments (`@asset` vs `@asset(key=...)`)
- `inspect.signature` for dependency extraction from type hints
- Singleton registry pattern (or explicit `Definitions` object)
- Pydantic for `AssetKey`, `AssetDefinition` models

**Deliverables:**
- `AssetKey` - namespaced identifier (group, name)
- `AssetDefinition` - metadata wrapper (key, deps, fn, return type)
- `@asset` decorator that registers to global/local registry
- `AssetRegistry` - stores definitions, validates no cycles

---

## Phase 2: Dependency Resolution & DAG

**Goal:** Build execution graph with topological sort.

```python
from lattice import Definitions, materialize

defs = Definitions(assets=[raw_users, cleaned_users, user_statistics])

# Resolve what to run for a target
plan = defs.resolve(target="user_statistics")
# -> ExecutionPlan(order=[raw_users, cleaned_users, user_statistics])

# Or materialize a subset
materialize(assets=[cleaned_users])  # Also runs raw_users
```

**Python patterns:**
- Graph representation (adjacency list)
- Kahn's algorithm or DFS for topological sort
- Cycle detection with clear error messages
- `__contains__`, `__iter__` protocol for plan objects

**Deliverables:**
- `DependencyGraph` - builds DAG from registry
- `ExecutionPlan` - ordered list of assets to materialize
- Subset selection (run only what's needed for target)
- Visualization helper (output DOT format for Graphviz)

---

## Phase 3: IO Managers & Materialization

**Goal:** Pluggable storage backends, actual execution.

```python
from lattice import IOManager, asset, materialize

class ParquetIOManager(IOManager):
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def load(self, key: AssetKey, annotation: type) -> Any:
        path = self.base_path / f"{key}.parquet"
        return pd.read_parquet(path)

    def store(self, key: AssetKey, value: Any) -> None:
        path = self.base_path / f"{key}.parquet"
        value.to_parquet(path)

# Use it
materialize(
    assets=[user_statistics],
    resources={"io_manager": ParquetIOManager(Path("./data"))}
)
```

**Python patterns:**
- Abstract base class with `@abstractmethod`
- Generic type hints (`IOManager[T]` if you want to get fancy)
- Context managers for resource lifecycle
- Dependency injection for resources

**Deliverables:**
- `IOManager` ABC with `load()` / `store()`
- `MemoryIOManager` - for testing (stores in dict)
- `FileIOManager` - pickle-based default
- `ParquetIOManager` - for DataFrames
- `Executor` - walks plan, manages IO, invokes asset functions

---

## Phase 4: Async Execution & Concurrency

**Goal:** Parallel execution of independent assets.

```python
@asset
async def fetch_api_a() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.example.com/a")
        return resp.json()

@asset
async def fetch_api_b() -> dict:
    ...

@asset
def combined(fetch_api_a: dict, fetch_api_b: dict) -> dict:
    """Sync asset - a and b fetched in parallel first."""
    return {**fetch_api_a, **fetch_api_b}

# Executor detects independent branches, runs concurrently
await materialize_async(assets=[combined], max_concurrency=4)
```

**Python patterns:**
- `asyncio.TaskGroup` for structured concurrency
- `asyncio.Semaphore` for concurrency limits
- Mixing sync/async callables (detect with `inspect.iscoroutinefunction`)
- `asyncio.to_thread` for running sync assets without blocking

**Deliverables:**
- `AsyncExecutor` - parallel execution within DAG levels
- Concurrency limits (global and per-asset-group)
- Proper cancellation handling
- Sync fallback executor for simpler use cases

---

## Phase 5: Partitions & Incremental Materialization

**Goal:** Time-partitioned assets, backfills.

```python
from lattice import asset, DailyPartition
from datetime import date

@asset(partitions=DailyPartition(start="2024-01-01"))
def daily_events(partition_key: date) -> pd.DataFrame:
    return fetch_events_for_date(partition_key)

@asset(partitions=DailyPartition(start="2024-01-01"))
def daily_summary(daily_events: pd.DataFrame, partition_key: date) -> dict:
    return {"date": partition_key, "count": len(daily_events)}

# Materialize specific partitions
materialize(assets=[daily_summary], partitions=["2024-01-15", "2024-01-16"])

# Backfill a range
materialize(assets=[daily_summary], partition_range=("2024-01-01", "2024-01-31"))
```

**Python patterns:**
- Generics for partition types (`Partition[K]`)
- Iterator protocol for partition ranges
- Metadata storage (what's been materialized)
- Property-based testing for partition logic

**Deliverables:**
- `PartitionDefinition` ABC
- `DailyPartition`, `MonthlyPartition`, `StaticPartition`
- Partition-aware IO managers (subdirectories/prefixes)
- Materialization metadata store (SQLite or JSON)

---

## Phase 6: Observability & Lineage

**Goal:** Track runs, lineage, and data quality.

```python
@asset
def validated_users(cleaned_users: pd.DataFrame) -> pd.DataFrame:
    return cleaned_users

@validated_users.check
def no_null_emails(df: pd.DataFrame) -> CheckResult:
    nulls = df["email"].isna().sum()
    return CheckResult(passed=nulls == 0, metadata={"null_count": nulls})

# After materialization
run = materialize(assets=[validated_users])
print(run.logs)          # Structured logs
print(run.lineage)       # What was read/written
print(run.check_results) # Data quality results
```

**Python patterns:**
- Structured logging with context (structlog)
- Event sourcing pattern for run history
- Decorator chaining (`.check` as method on wrapped asset)

**Deliverables:**
- `RunResult` with timing, logs, lineage
- Asset checks framework
- SQLite-backed run history
- Simple CLI or TUI for viewing runs

---

## Phase 7: AWS Deployment

**Goal:** Run Lattice on AWS within $10-20/month budget.

```
EventBridge ──▶ Lambda ──▶ Lattice ──▶ S3
   (cron)       (runner)   (materialize)  (IO manager)
```

**Cost breakdown:**
| Service | Usage | Est. Cost |
|---------|-------|-----------|
| S3 | 1-5 GB storage | ~$0.12 |
| Lambda | 100 invocations/day, 512MB, 2min | ~$2-5 |
| EventBridge | Scheduler rules | Free tier |
| Athena | Occasional queries | ~$1-3 |
| **Total** | | **~$5-10/month** |

**Deliverables:**
- `S3IOManager` implementation
- Lambda handler that invokes `materialize()`
- Terraform modules (integrate with existing `infrastructure/` patterns)
- CloudWatch logging integration

---

## Project Structure

```
lattice/
├── pyproject.toml
├── PROJECT_PLAN.md
├── src/
│   └── lattice/
│       ├── __init__.py        # Public API exports
│       ├── asset.py           # @asset decorator, AssetDefinition
│       ├── registry.py        # AssetRegistry, Definitions
│       ├── graph.py           # DependencyGraph, topological sort
│       ├── plan.py            # ExecutionPlan
│       ├── executor.py        # Sync/Async executors
│       ├── io/
│       │   ├── __init__.py
│       │   ├── base.py        # IOManager ABC
│       │   ├── memory.py
│       │   ├── file.py
│       │   ├── parquet.py
│       │   └── s3.py
│       ├── partitions/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── time.py
│       │   └── static.py
│       ├── checks.py          # Data quality checks
│       ├── run.py             # RunResult, history
│       └── cli.py             # Optional CLI
├── tests/
│   ├── conftest.py
│   ├── test_asset.py
│   ├── test_graph.py
│   ├── test_executor.py
│   └── test_partitions.py
└── examples/
    ├── simple_pipeline.py
    └── async_pipeline.py
```

---

## Phase Order Rationale

| Phase | Why This Order |
|-------|----------------|
| 1-2 | Core mental model - decorator + DAG resolution |
| 3 | Actually run things - immediate feedback |
| 4 | Complex Python - async patterns |
| 5 | Partitions are where orchestrators get interesting |
| 6 | Observability makes it "real" |
| 7 | Deploy your creation |

---

## Python Patterns Covered

- **Decorators**: with/without arguments, preserving metadata
- **Type hints**: generics, `TypeVar`, runtime inspection
- **Pydantic**: validation, serialization, immutability
- **Abstract base classes**: `@abstractmethod`, protocols
- **Async/await**: `TaskGroup`, semaphores, mixed sync/async
- **Testing**: pytest fixtures, mocking, property-based (Hypothesis)
- **Graph algorithms**: topological sort, cycle detection
- **Dependency injection**: resources, context managers
- **Structured logging**: structlog, context propagation
