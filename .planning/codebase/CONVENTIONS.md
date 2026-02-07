# Coding Conventions

**Analysis Date:** 2026-02-06

## Naming Patterns

**Files:**
- Module files use `snake_case`: `asset.py`, `execution.py`, `log_capture.py`
- Test files follow pattern `test_<module_name>.py`: `test_asset.py`, `test_executor.py`, `test_io.py`
- Test subdirectories mirror source structure: `tests/test_observability/` mirrors `src/lattice/observability/`
- Package initialization files: `__init__.py` (Python standard)

**Functions & Methods:**
- Function names use `snake_case`: `_extract_dependencies()`, `topological_sort()`, `get_logger()`, `execute()`
- Private/internal functions prefix with single underscore: `_extract_dependencies()`, `_extract_return_type()`, `_configured`
- Async functions follow same convention: `async def execute_async()`, `async def broadcast()`
- Decorated methods and wrapper functions preserve naming: `@overload`, `@abstractmethod`, `@wraps(func)`

**Variables:**
- Local and instance variables use `snake_case`: `asset_key`, `target_registry`, `dependency_params`
- Constants use `UPPER_SNAKE_CASE`: None used directly in codebase (rely on Pydantic `frozen=True` for immutability)
- Type variables use `PascalCase`: `P = ParamSpec("P")`, `R = TypeVar("R")`, `T = TypeVar("T")`
- Protected attributes use single underscore prefix: `_storage`, `_configured`, `_checks`

**Types & Classes:**
- Class names use `PascalCase`: `AssetKey`, `AssetDefinition`, `AssetWithChecks`, `ExecutionPlan`, `DependencyGraph`
- Exception classes use `PascalCase` with `Error` suffix: `CyclicDependencyError`
- Pydantic model names use `PascalCase`: `AssetKey`, `RunRecord`, `CheckDefinition`

## Code Style

**Formatting:**
- Tool: `ruff` (via `ruff-format`)
- Line length: 100 characters (configured in `pyproject.toml`)
- Indentation: 4 spaces (Python standard)
- String quotes: Double quotes preferred (enforced by ruff-format)
- Trailing whitespace: Removed by pre-commit hook

**Linting:**
- Tool: `ruff`
- Configuration in `pyproject.toml`: `[tool.ruff]` section
- Selected rules: `E` (pycodestyle errors), `F` (Pyflakes), `I` (import sorting), `UP` (upgrades), `B` (flake8-bugbear), `SIM` (simplifications), `PTH` (pathlib)
- Import sorting: Handled by ruff with `I` rule
- Pre-commit integration: `.pre-commit-config.yaml` runs `ruff --fix` and `ruff-format` automatically

**Type Checking:**
- Tool: `mypy`
- Mode: `strict` (enabled in `pyproject.toml`)
- Python version: 3.11
- All code should be fully type-annotated; any type ignores should be justified in comments

## Import Organization

**Order:**
1. `from __future__ import annotations` (when needed for forward references)
2. Standard library imports: `import asyncio`, `import logging`, `from pathlib import Path`
3. Third-party imports: `from pydantic import BaseModel`, `import polars as pl`
4. Local imports: `from lattice.models import AssetKey`, `from lattice.registry import AssetRegistry`
5. TYPE_CHECKING block (for circular import avoidance): `if TYPE_CHECKING: from lattice.observability.checks import AssetWithChecks`

**Path Aliases:**
- No explicit path aliases configured; projects use absolute imports from `lattice` package root
- Import pattern: `from lattice.models import AssetKey` (not relative imports)

**Circular Import Avoidance:**
Pattern used in `asset.py` and `exceptions.py`:
```python
if TYPE_CHECKING:
    from lattice.observability.checks import AssetWithChecks
```
Defers import to type-checking only, imports at runtime inside function where needed.

## Error Handling

**Patterns:**
- Raise custom exceptions for domain errors: `CyclicDependencyError`, `KeyError` for missing assets
- Use `raise NotImplementedError()` for optional/override methods in base classes (see `IOManager.delete()`)
- Exception attributes store context: `CyclicDependencyError.cycle` stores the cycle path
- Use `with pytest.raises()` for exception testing: `with pytest.raises(KeyError, match="test")`
- Generic exception catching (`except Exception:`) limited to specific cases (e.g., `_extract_return_type()` falls back on type hint extraction failure)

**Example from `exceptions.py`:**
```python
class CyclicDependencyError(Exception):
    def __init__(self, cycle: list["AssetKey"]) -> None:
        self.cycle = cycle
        cycle_str = " -> ".join(str(key) for key in cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_str}")
```

## Logging

**Framework:** Python standard `logging` module with custom configuration via `logging.config.fileConfig`

**Initialization:**
- Function `configure_logging()` in `lattice/logging/config.py` handles setup
- Fallback to `logging.basicConfig()` if config file not found
- Uses INI-style configuration file (standard Python logging format)

**Patterns:**
- Get logger once per module: `logger = logging.getLogger(__name__)`
- Log at appropriate levels:
  - `logger.info()` for significant events: `logger.info("Asset registered: %s", asset_key)`
  - `logger.debug()` for detailed execution flow: `logger.debug("Asset %s depends on: %s", asset_key, [...])`
  - `logger.warning()` for potential issues: `logger.warning("Logging config not found...")`
- Use `%` formatting with args separate: `logger.info("Asset %s", key_name)` (not f-strings)

## Comments

**When to Comment:**
- Module-level docstring explains purpose: Every module has triple-quoted docstring at top
- Complex logic explained inline: Comments in `_extract_return_type()` explain exception handling
- TYPE_CHECKING pattern explained: `# TYPE_CHECKING is True only during static analysis...` in `exceptions.py`
- Parameter mapping explained: Comments in `_extract_dependencies()` explain special parameter exclusion

**JSDoc/TSDoc Style (Python: docstrings):**
- Google-style docstrings used throughout
- Format:
  ```python
  def function(param1: str) -> int:
      """
      Short one-line description.

      Longer description with more detail if needed.

      Parameters
      ----------
      param1 : str
          What this parameter means.

      Returns
      -------
      int
          What is returned.

      Raises
      ------
      KeyError
          When this might be raised.
      """
  ```
- All public functions documented with parameters, returns, and raises sections
- Private functions (leading `_`) may have minimal docstrings

**Example from `models.py`:**
```python
def __str__(self) -> str:
    """
    Return string representation of the asset key.

    Returns
    -------
    str
        Format "group/name" if the group is not default, otherwise just "name".
    """
```

## Function Design

**Size:**
- Small functions preferred; `_extract_dependencies()` is ~25 lines, `_extract_return_type()` is ~10 lines
- Complex operations like `ExecutionPlan.resolve()` reach ~50 lines but are well-commented

**Parameters:**
- Use explicit keyword-only parameters for optional arguments: `def asset(..., key: AssetKey | None = None, deps: dict[str, AssetKey] | None = None)`
- Prefer `@overload` decorators for multiple signatures: `asset.py` has two `@overload` definitions before implementation

**Return Values:**
- Use union types for optional returns: `type | None`
- Return immutable tuples for sequences: `tuple[AssetKey, ...]` instead of lists
- Return instances frozen with Pydantic `ConfigDict(frozen=True)` for immutability

**Generic/Async Handling:**
- Async wrapper functions use `@wraps(func)` to preserve metadata: `async def async_wrapper(*args: Any, **kwargs: Any) -> Any:`
- Dual sync/async support: Both wrappers used; async detected with `inspect.iscoroutinefunction(func)`

## Module Design

**Exports:**
- Package `__init__.py` files re-export public API: `lattice/__init__.py` exports `asset`, `AssetKey`, `AssetRegistry`, etc.
- Internal modules prefixed with `_` when needed, but most modules are directly importable
- Example in `observability/__init__.py`: Large functions and classes re-exported for public use

**Barrel Files:**
- `lattice/__init__.py` serves as barrel file, exporting core decorators and models
- `lattice/io/__init__.py` exports IO manager interfaces: `from lattice.io.base import IOManager`
- `lattice/observability/history/__init__.py` exports history storage classes
- Pattern: `from .module import Class, function` in `__init__.py` files

**Module Dependencies:**
- Core models (`models.py`) have no dependencies on other modules except Pydantic
- Decorators (`asset.py`) depend on models and registry
- Observability modules have minimal cross-dependencies via `TYPE_CHECKING`
- Base classes (abc) are depended on but don't depend on implementations

---

*Convention analysis: 2026-02-06*
