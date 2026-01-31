"""Lattice: An asset-centric orchestration framework."""

from importlib.metadata import version

from lattice.asset import asset
from lattice.exceptions import CyclicDependencyError
from lattice.executor import (
    AssetExecutionResult,
    AssetStatus,
    ExecutionResult,
    ExecutionState,
    Executor,
    materialize,
)
from lattice.graph import DependencyGraph
from lattice.io import FileIOManager, IOManager, MemoryIOManager
from lattice.models import AssetDefinition, AssetKey
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
    "ExecutionResult",
    "ExecutionState",
    "Executor",
    "materialize",
    # IO
    "IOManager",
    "MemoryIOManager",
    "FileIOManager",
]

# Optional ParquetIOManager
try:
    from lattice.io import ParquetIOManager  # noqa: F401

    __all__.append("ParquetIOManager")
except ImportError:
    pass

__version__ = version("lattice")
