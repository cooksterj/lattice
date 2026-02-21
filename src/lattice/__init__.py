"""Lattice: An asset-centric orchestration framework."""

from importlib.metadata import version

from lattice.asset import asset
from lattice.exceptions import CyclicDependencyError
from lattice.executor import (
    AssetExecutionResult,
    AssetStatus,
    AsyncExecutor,
    ExecutionResult,
    ExecutionState,
    Executor,
    materialize,
    materialize_async,
)
from lattice.graph import DependencyGraph
from lattice.io import FileIOManager, IOManager, MemoryIOManager
from lattice.logging import configure_logging, get_logger
from lattice.models import AssetDefinition, AssetKey
from lattice.observability import (
    AssetWithChecks,
    CheckDefinition,
    CheckRegistry,
    CheckResult,
    CheckStatus,
    LineageEvent,
    LineageIOManager,
    LineageTracker,
    LogEntry,
    RunHistoryStore,
    RunRecord,
    RunResult,
    SQLiteRunHistoryStore,
    get_global_check_registry,
    materialize_with_observability,
)
from lattice.plan import ExecutionPlan
from lattice.registry import AssetRegistry, get_global_registry

__all__ = [
    # Core
    "asset",
    "AssetDefinition",
    "AssetKey",
    "AssetRegistry",
    "get_global_registry",
    # Graph
    "CyclicDependencyError",
    "DependencyGraph",
    "ExecutionPlan",
    # Execution
    "AssetExecutionResult",
    "AssetStatus",
    "AsyncExecutor",
    "ExecutionResult",
    "ExecutionState",
    "Executor",
    "materialize",
    "materialize_async",
    # IO
    "IOManager",
    "MemoryIOManager",
    "FileIOManager",
    # Logging
    "configure_logging",
    "get_logger",
    # Observability
    "AssetWithChecks",
    "CheckDefinition",
    "CheckRegistry",
    "CheckResult",
    "CheckStatus",
    "LineageEvent",
    "LineageIOManager",
    "LineageTracker",
    "LogEntry",
    "RunHistoryStore",
    "RunRecord",
    "RunResult",
    "SQLiteRunHistoryStore",
    "get_global_check_registry",
    "materialize_with_observability",
]

# Optional ParquetIOManager
try:
    from lattice.io import ParquetIOManager  # noqa: F401

    __all__.append("ParquetIOManager")
except ImportError:
    pass

# dbt integration
from lattice.dbt import (  # noqa: F401
    DBT_GROUP,
    DbtModelInfo,
    DbtTestInfo,
    ManifestParser,
    dbt_assets,
    load_dbt_manifest,
)

__all__.extend(
    [
        "DBT_GROUP",
        "DbtModelInfo",
        "DbtTestInfo",
        "ManifestParser",
        "dbt_assets",
        "load_dbt_manifest",
    ]
)

__version__ = version("lattice")
