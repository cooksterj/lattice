# Testing Patterns

**Analysis Date:** 2026-02-06

## Test Framework

**Runner:**
- Framework: `pytest` (>= 9.0.2)
- Configuration: `pyproject.toml` under `[tool.pytest.ini_options]`
- Test paths: `tests/` directory (configured in `pyproject.toml`)
- Async support: `pytest-asyncio` (>= 1.3.0) with `asyncio_mode = "auto"` for automatic event loop handling

**Assertion Library:**
- Standard Python `assert` statements
- Pydantic `ValidationError` for model validation testing

**Run Commands:**
```bash
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest -k "test_name"           # Run specific tests by name pattern
pytest --asyncio-mode=auto      # Async tests (configured by default)
pytest -x                       # Stop on first failure
pytest --tb=short               # Shorter traceback format
```

Coverage is not enforced but can be run with pytest-cov.

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory mirroring source structure
- Pattern: `tests/test_<module>.py` for source module `src/lattice/<module>.py`
- Subdirectories: `tests/test_observability/` mirrors `src/lattice/observability/`

**Naming:**
- Test files: `test_<module_name>.py` (prefix with `test_`)
- Test classes: `Test<FeatureName>` (PascalCase with leading capital T)
- Test methods: `test_<specific_behavior>` (snake_case with `test_` prefix)
- Fixture files: `conftest.py` (shared pytest fixtures)

**Structure:**
```
tests/
├── conftest.py                 # Shared fixtures (global)
├── test_asset.py               # Tests for @asset decorator and models
├── test_executor.py            # Tests for execution engine
├── test_graph.py               # Tests for dependency graph
├── test_io.py                  # Tests for IO managers
├── test_plan.py                # Tests for execution plan
├── test_web.py                 # Tests for web/API layer
├── test_cli.py                 # Tests for CLI
├── test_observability/         # Observability feature tests
│   ├── test_checks.py          # Data quality checks
│   ├── test_history_sqlite.py  # SQLite history store
│   ├── test_integration.py     # Integration tests
│   ├── test_lineage.py         # Lineage tracking
│   ├── test_log_capture.py     # Log capture
│   └── test_models.py          # Observability models
```

## Test Structure

**Suite Organization:**
Tests organized in classes grouping related functionality. From `test_asset.py`:

```python
class TestAssetKey:
    """Tests for AssetKey model."""
    def test_create_with_name_only(self) -> None:
        ...
    def test_create_with_group(self) -> None:
        ...

class TestAssetDecorator:
    """Tests for the @asset decorator."""
    def test_basic_decoration(self) -> None:
        ...
    def test_with_explicit_key(self) -> None:
        ...

class TestAssetRegistry:
    """Tests for AssetRegistry."""
    def test_register_and_get(self, registry: AssetRegistry) -> None:
        ...
```

**Setup & Teardown:**
- Global fixture `clean_global_registries()` (autouse=True) in `conftest.py` clears registries before each test
- No explicit setup/teardown; fixtures handle initialization
- Temporary directories created with `tempfile.TemporaryDirectory()` context manager (in test methods, not fixtures)

**Assertion Patterns:**
From `test_asset.py`:
```python
def test_create_with_name_only(self) -> None:
    key = AssetKey(name="my_asset")
    assert key.name == "my_asset"
    assert key.group == "default"

def test_immutable(self) -> None:
    from pydantic import ValidationError
    key = AssetKey(name="my_asset")
    with pytest.raises(ValidationError):
        key.name = "other"  # type: ignore[misc]
```

Common patterns:
- Direct equality: `assert result == expected`
- Exception testing: `with pytest.raises(ErrorType, match="pattern")`
- Boolean checks: `assert io.has(key)`, `assert not io.has(key)`
- Container membership: `assert "key" in registry`, `assert key in io`

## Mocking

**Framework:** No explicit mocking framework (uses pytest directly)

**Patterns:**
Minimal mocking; tests use real implementations instead:
- `MemoryIOManager` for storage tests (not mocking `IOManager`)
- `AssetRegistry` instantiated directly for registry tests
- Fixtures provide fresh instances rather than mocks

From `test_executor.py` - real object usage:
```python
def test_execute_single_asset(self, registry: AssetRegistry) -> None:
    @asset(registry=registry)
    def source() -> int:
        return 42

    plan = ExecutionPlan.resolve(registry)
    io = MemoryIOManager()
    executor = Executor(io_manager=io)
    result = executor.execute(plan)

    assert result.status == AssetStatus.COMPLETED
```

**What to Mock:**
- Nothing explicitly required; codebase prefers real lightweight implementations
- When needed: Use Pydantic `ValidationError` for model validation testing

**What NOT to Mock:**
- Don't mock `AssetKey`, `AssetDefinition`, or core models - test with real instances
- Don't mock `IOManager` implementations - use concrete `MemoryIOManager` or `FileIOManager`
- Don't mock registry operations - use real `AssetRegistry`

## Fixtures and Factories

**Test Data:**
Global fixture in `conftest.py`:
```python
@pytest.fixture(autouse=True)
def clean_global_registries() -> None:
    """Clear global registries before each test."""
    get_global_registry().clear()
    get_global_check_registry().clear()

@pytest.fixture
def registry() -> AssetRegistry:
    """Provide a fresh isolated registry for testing."""
    return AssetRegistry()
```

Asset creation in tests uses `@asset` decorator directly:
```python
@asset(registry=registry)
def my_asset() -> int:
    return 42
```

Complex fixture from `test_executor.py`:
```python
def test_execute_linear_chain(self, registry: AssetRegistry) -> None:
    @asset(registry=registry)
    def a() -> int:
        return 1

    @asset(registry=registry)
    def b(a: int) -> int:
        return a + 10

    @asset(registry=registry)
    def c(b: int) -> int:
        return b + 100
```

**Location:**
- Global fixtures: `tests/conftest.py`
- Module-specific fixtures: In module's test file (not currently used)
- No separate factory files; inline creation with decorators

## Coverage

**Requirements:** Not enforced (no minimum coverage threshold configured)

**View Coverage:**
Not configured in `pyproject.toml`; can be added with:
```bash
pytest --cov=lattice --cov-report=html
```

## Test Types

**Unit Tests:**
- Scope: Individual classes and functions in isolation
- Approach: Test single unit with dependencies mocked or stubbed
- Example (`test_asset.py`): Tests `AssetKey` model validation, `@asset` decorator parameter handling, registry operations
- Location: Primary test files like `test_asset.py`, `test_models.py`

**Integration Tests:**
- Scope: Multiple components working together
- Approach: Real instances of registry, executor, IO managers, etc.
- Example (`test_executor.py`): Tests `Executor` with real `ExecutionPlan`, `AssetRegistry`, `MemoryIOManager`
- Location: Larger test files like `test_executor.py` (1031 lines), `test_web.py` (654 lines), `test_observability/test_integration.py` (336 lines)

**E2E Tests:**
- Framework: Not used (codebase is a framework itself, not an application)
- Alternative: Web API tests in `test_web.py` use `httpx` client to test endpoints (similar scope)

## Common Patterns

**Async Testing:**
Pattern from `test_executor.py`:
```python
@pytest.mark.asyncio
async def test_materialize_async(self, registry: AssetRegistry) -> None:
    @asset(registry=registry)
    async def async_source() -> int:
        return 42

    io = MemoryIOManager()
    result = await materialize_async(registry, io)
    assert result.status == AssetStatus.COMPLETED
```

With `asyncio_mode = "auto"` in `pyproject.toml`, pytest-asyncio handles event loop automatically.

**Error Testing:**
From `test_asset.py`:
```python
def test_empty_name_rejected(self) -> None:
    with pytest.raises(ValueError):
        AssetKey(name="")

def test_immutable(self) -> None:
    from pydantic import ValidationError
    key = AssetKey(name="my_asset")
    with pytest.raises(ValidationError):
        key.name = "other"  # type: ignore[misc]
```

Pattern: Use `pytest.raises()` context manager with optional `match` parameter for exception message testing.

**Exception Message Matching:**
From `test_io.py`:
```python
def test_load_missing_raises(self) -> None:
    io = MemoryIOManager()
    with pytest.raises(KeyError, match="test"):
        io.load(AssetKey(name="test"))
```

**Graph/Dependency Testing:**
From `test_graph.py` and `test_plan.py`:
```python
def test_linear_chain_full(self, registry: AssetRegistry) -> None:
    @asset(registry=registry)
    def a() -> int:
        return 1

    @asset(registry=registry)
    def b(a: int) -> int:
        return a + 1

    plan = ExecutionPlan.resolve(registry)
    keys = [asset.key for asset in plan]

    # Verify ordering
    assert keys.index(AssetKey(name="a")) < keys.index(AssetKey(name="b"))
```

**Parameterized Tests:**
Not heavily used; specific cases tested individually rather than parametrized.

**Grouped Asset Tests:**
From `test_asset.py`:
```python
def test_explicit_deps_for_grouped_assets(self) -> None:
    """Test that deps parameter allows explicit dependency specification."""
    @asset(
        key=AssetKey(name="dashboard", group="analytics"),
        deps={
            "revenue": AssetKey(name="daily_revenue", group="analytics"),
            "stats": AssetKey(name="user_stats", group="analytics"),
        },
    )
    def dashboard(revenue: dict, stats: dict) -> dict:
        return {"revenue": revenue, "stats": stats}

    assert dashboard.dependencies == (
        AssetKey(name="daily_revenue", group="analytics"),
        AssetKey(name="user_stats", group="analytics"),
    )
```

**File System Tests:**
From `test_io.py`:
```python
def test_file_structure(self) -> None:
    """Files are organized by group."""
    with tempfile.TemporaryDirectory() as tmpdir:
        io = FileIOManager(tmpdir)
        io.store(AssetKey(name="data", group="raw"), 1)
        io.store(AssetKey(name="data", group="processed"), 2)

        base = Path(tmpdir)
        assert (base / "raw" / "data.pkl").exists()
        assert (base / "processed" / "data.pkl").exists()
```

Pattern: Use `tempfile.TemporaryDirectory()` context manager for filesystem isolation.

## Test Dependencies

**Testing Requirements:**
From `pyproject.toml` dev dependencies:
- `pytest>=9.0.2` - Test runner
- `pytest-asyncio>=1.3.0` - Async test support
- `httpx>=0.28.0` - HTTP client for API testing
- `hypothesis>=6.151.2` - Property-based testing library (present but not heavily used)
- `mypy>=1.19.1` - Type checking
- `ruff>=0.14.14` - Linting

**Installed via:**
```bash
uv pip install -e ".[dev]"    # Using uv package manager
pip install -e ".[dev]"        # Using pip
```

---

*Testing analysis: 2026-02-06*
