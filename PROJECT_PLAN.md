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

**Goal:** Build execution graph with topological sort, plus web-based visualization.

```python
from lattice import asset, ExecutionPlan, get_global_registry
from lattice.web.app import serve

@asset
def raw_data() -> dict:
    return {"value": 1}

@asset
def processed(raw_data: dict) -> dict:
    return {"processed": raw_data["value"] * 2}

# Resolve execution plan
plan = ExecutionPlan.resolve(get_global_registry(), target="processed")
for asset_def in plan:
    print(f"Execute: {asset_def.key}")

# Start visualization server
serve(host="127.0.0.1", port=8000)
# Open http://localhost:8000
```

**Python patterns:**
- Graph representation (adjacency list)
- Kahn's algorithm or DFS for topological sort
- Cycle detection with clear error messages
- `__contains__`, `__iter__` protocol for plan objects
- FastAPI for REST endpoints
- D3.js force-directed graph visualization

**Deliverables:**
- `DependencyGraph` - builds DAG from registry
- `ExecutionPlan` - ordered list of assets to materialize
- Subset selection (run only what's needed for target)
- `CyclicDependencyError` - exception with cycle path for debugging

**Web Visualization:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main HTML visualization page |
| `/api/graph` | GET | Graph data (nodes + edges) for D3.js |
| `/api/assets/{key}` | GET | Asset detail (dependencies, dependents, metadata) |
| `/api/plan` | GET | Execution plan (optional `?target=` query param) |
| `/health` | GET | Health check for containers |

**Deployment Options:**
- **Local development:** `serve(host="127.0.0.1", port=8000)` for localhost access
- **Docker (future):** Containerized deployment to EC2 or ECS for team-wide access
  - Dockerfile with uvicorn + gunicorn for production
  - ECS Fargate for serverless container hosting
  - EC2 for persistent instance with lower cost at scale

**Optional dependencies** (install with `pip install lattice[web]`):
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.34.0`
- `jinja2>=3.1.0`

**UI Beautification:**

| Component | Implementation |
|-----------|----------------|
| CSS Framework | Tailwind CSS via CDN (no build step) |
| Color Scheme | Dark mode default with light mode toggle |
| Typography | Inter font for UI, JetBrains Mono for code |
| Icons | Lucide icons for actions and status indicators |
| Animations | Smooth transitions for node hover/selection |

Visual enhancements:
- **Graph nodes:** Rounded rectangles with gradient fills, group-based coloring
- **Edges:** Animated directional arrows showing dependency flow
- **Sidebar:** Glassmorphism panel for asset details with syntax-highlighted metadata
- **Status indicators:** Color-coded badges (success/pending/error) for materialization state
- **Responsive layout:** Collapsible sidebar, mobile-friendly graph controls
- **Loading states:** Skeleton loaders and spinners during API calls
- **Tooltips:** Rich hover cards showing asset summary without clicking

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

**Web UI Enhancements:**

| Feature | Description |
|---------|-------------|
| **Execution Status Indicator** | Real-time visual indicator showing which assets are currently running |
| **Memory Usage Summary** | Live memory consumption display during asset materialization |

Execution monitoring components:
- **Asset status badges:** Dynamic color-coded indicators (idle/running/completed/failed) on graph nodes
- **Pulsing animation:** Animated glow effect on nodes currently being materialized
- **Progress sidebar:** List view showing execution queue with current status per asset
- **Memory metrics panel:** Real-time display of process memory usage (RSS, heap) during execution
- **Memory sparkline:** Mini chart showing memory consumption over time during the run
- **Peak memory indicator:** Highlight maximum memory usage reached during materialization

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/execution/status` | GET | Current execution state (running assets, queue) |
| `/api/execution/memory` | GET | Memory usage snapshot (current, peak, timeline) |
| `/api/execution/start` | POST | Trigger materialization for target asset(s) |
| WebSocket `/ws/execution` | WS | Real-time updates for status and memory metrics |

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

**Goal:** Time-partitioned assets, backfills, and web UI date selection.

```python
from lattice import asset
from datetime import date

@asset
def daily_events(partition_key: date) -> pd.DataFrame:
    """Asset receives partition_key when executed with a date."""
    return fetch_events_for_date(partition_key)

@asset
def daily_summary(daily_events: pd.DataFrame, partition_key: date) -> dict:
    """Downstream assets also receive the partition_key."""
    return {"date": partition_key, "count": len(daily_events)}

# Materialize with a specific date (partition_key injected automatically)
materialize(assets=[daily_summary], execution_date=date(2024, 1, 15))

# Backfill a range (executes sequentially for each date)
materialize(
    assets=[daily_summary],
    execution_date=date(2024, 1, 1),
    execution_date_end=date(2024, 1, 31),
)
```

**Python patterns:**
- `inspect.signature` to detect if asset accepts `partition_key` parameter
- Iterator protocol for partition ranges
- Sequential execution loop for date ranges
- WebSocket messages for partition progress

**Deliverables:**
- `partition_key` parameter injection in `Executor` and `AsyncExecutor`
- `execution_date` and `execution_date_end` fields in `ExecutionStartRequest`
- Date range iteration in `ExecutionManager.run_execution()`
- New WebSocket message types: `partition_start`, `partition_complete`

**Web UI Enhancements:**

| Feature | Description |
|---------|-------------|
| **Date Picker Panel** | Select single date or date range before execution |
| **Mode Toggle** | Switch between SINGLE and RANGE date modes |
| **Date Preview** | Shows selected date(s) and day count for ranges |
| **Partition Progress** | Real-time indicator showing current date being executed |

Date selection panel (above Execute button):
```
+---------------------------------------+
|  // PARTITION DATE                    |
+---------------------------------------+
|  [SINGLE]  [RANGE]                    |
|                                       |
|  EXECUTION DATE                       |
|  [____2024-01-15____]                 |
|                                       |
|  > 2024-01-15                         |
+---------------------------------------+
|  [>  EXECUTE  ]                       |
+---------------------------------------+
```

**Execution Flow (Date Range):**

1. User selects date range (e.g., 2024-01-01 to 2024-01-03)
2. Backend generates date list and executes sequentially
3. For each date:
   - Broadcast `partition_start` with current date info
   - Execute full pipeline with `partition_key` injected
   - Broadcast `partition_complete` with results
4. Frontend resets node states between partitions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/execution/start` | POST | Now accepts `execution_date` and `execution_date_end` |
| WebSocket `/ws/execution` | WS | New message types: `partition_start`, `partition_complete` |

**Future Deliverables (not in initial implementation):**
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
print(run.logs)          # Captured logs from execution
print(run.lineage)       # What was read/written
print(run.check_results) # Data quality results
```

**Python patterns:**
- Event sourcing pattern for run history
- Decorator chaining (`.check` as method on wrapped asset)
- In-memory log capture during execution

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
│       ├── cli.py             # Optional CLI
│       └── integrations/
│           └── dbt/
│               ├── __init__.py
│               ├── manifest.py
│               ├── assets.py
│               ├── selectors.py
│               └── io.py
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
| 8 | Integrate with existing dbt workflows |

---

## Phase 8: dbt Integration

**Goal:** Import dbt models as Lattice assets with group support.

```python
from lattice import asset, AssetKey
from lattice.integrations.dbt import DbtManifest, dbt_assets

# Load dbt project manifest
manifest = DbtManifest.from_project("./my_dbt_project")

# Import all dbt models as Lattice assets
@dbt_assets(manifest=manifest)
def my_dbt_models():
    """All models become Lattice assets with dependencies preserved."""
    pass

# Or selectively import with group filtering
@dbt_assets(manifest=manifest, select="group:finance")
def finance_models():
    """Only models in the 'finance' group."""
    pass

# Mix dbt assets with native Lattice assets
@asset(key=AssetKey(name="enriched_report", group="analytics"))
def enriched_report(
    stg_orders: dict,  # From dbt
    external_api_data: dict,  # Native Lattice asset
) -> dict:
    """Combine dbt model output with external data."""
    return {**stg_orders, **external_api_data}
```

**dbt Concepts Mapped to Lattice:**

| dbt Concept | Lattice Equivalent |
|-------------|-------------------|
| Model | `AssetDefinition` |
| `ref()` dependencies | `AssetDefinition.dependencies` |
| dbt Group | `AssetKey.group` |
| Tags | `AssetDefinition.metadata["tags"]` |
| Description | `AssetDefinition.description` |
| Materialization | `IOManager` strategy |
| Tests | Asset checks (Phase 6) |
| Sources | Source assets with no dependencies |

**dbt Groups Integration:**

dbt groups (introduced in dbt 1.5) provide access control and organization:

```yaml
# dbt_project.yml
groups:
  - name: finance
    owner:
      name: Finance Team
      email: finance@company.com

# models/staging/stg_orders.yml
models:
  - name: stg_orders
    group: finance
    access: protected
```

Lattice respects these groups:

```python
# Group becomes AssetKey.group
manifest = DbtManifest.from_project("./dbt_project")

for model in manifest.models:
    print(f"{model.name} -> group: {model.group}")
    # stg_orders -> group: finance
    # stg_customers -> group: marketing

# Filter by group
finance_assets = manifest.select("group:finance")
```

**Python patterns:**
- JSON parsing of dbt `manifest.json` and `run_results.json`
- Factory pattern for creating assets from external metadata
- Selector syntax parsing (dbt's `select` grammar)
- Lazy loading of dbt artifacts

**Deliverables:**
- `DbtManifest` - parser for dbt `manifest.json`
- `@dbt_assets` decorator - bulk import dbt models
- Group mapping (`dbt group` → `AssetKey.group`)
- Dependency resolution from `ref()` calls
- Source asset creation from dbt sources
- Selector support (`--select`, `--exclude` patterns)
- `DbtCloudIOManager` - optional integration for dbt Cloud runs

**File Structure:**

```
lattice/
└── integrations/
    └── dbt/
        ├── __init__.py      # Public API
        ├── manifest.py      # DbtManifest parser
        ├── assets.py        # @dbt_assets decorator
        ├── selectors.py     # dbt selector syntax parser
        └── io.py            # DbtCloudIOManager
```

**Web UI Enhancements:**

| Feature | Description |
|---------|-------------|
| **dbt Badge** | Visual indicator on nodes imported from dbt |
| **Group Filtering** | Sidebar filter to show/hide assets by dbt group |
| **Materialization Type** | Icon showing dbt materialization (table/view/incremental) |
| **dbt Cloud Link** | Direct link to model in dbt Cloud (if configured) |

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
- **Logging**: INI-based configuration, in-memory log capture
- **External integrations**: JSON manifest parsing, factory patterns, selector DSLs
