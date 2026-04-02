"""Top-level materialize functions for asset execution.

This module provides simple entry points for executing assets without
manually constructing plans and executors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lattice.executor.models import ExecutionResult
from lattice.io.base import IOManager
from lattice.models import AssetKey
from lattice.plan import ExecutionPlan

# TYPE_CHECKING block for imports only needed by type checkers (mypy, pyright).
# AssetRegistry is imported here to avoid circular imports at runtime:
# registry.py imports from models.py, and this module uses AssetRegistry
# only in type annotations for the optional registry parameter.
if TYPE_CHECKING:
    from lattice.registry import AssetRegistry


def materialize(
    registry: AssetRegistry | None = None,
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
) -> ExecutionResult:
    """
    Convenience function to materialize assets.

    Creates an ExecutionPlan and executes it with the given IO manager.

    Parameters
    ----------
    registry : AssetRegistry, optional
        Registry containing asset definitions.
        Defaults to the global registry.
    target : AssetKey or str, optional
        Target asset to materialize (with dependencies).
        If None, materializes all assets.
    io_manager : IOManager, optional
        Storage backend.
        Defaults to MemoryIOManager.

    Returns
    -------
    ExecutionResult
        Summary of the materialization run.
    """
    from lattice.executor.sync import Executor
    from lattice.registry import get_global_registry

    if registry is None:
        registry = get_global_registry()

    plan = ExecutionPlan.resolve(registry, target=target)
    executor = Executor(io_manager=io_manager)
    return executor.execute(plan)


async def materialize_async(
    registry: AssetRegistry | None = None,
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
    max_concurrency: int = 4,
) -> ExecutionResult:
    """
    Async convenience function to materialize assets with parallel execution.

    Creates an ExecutionPlan and executes it with the AsyncExecutor,
    running independent assets concurrently.

    Parameters
    ----------
    registry : AssetRegistry, optional
        Registry containing asset definitions.
        Defaults to the global registry.
    target : AssetKey or str, optional
        Target asset to materialize (with dependencies).
        If None, materializes all assets.
    io_manager : IOManager, optional
        Storage backend.
        Defaults to MemoryIOManager.
    max_concurrency : int, optional
        Maximum number of assets to execute in parallel.
        Defaults to 4.

    Returns
    -------
    ExecutionResult
        Summary of the materialization run.
    """
    from lattice.executor.async_executor import AsyncExecutor
    from lattice.registry import get_global_registry

    if registry is None:
        registry = get_global_registry()

    plan = ExecutionPlan.resolve(registry, target=target)
    executor = AsyncExecutor(io_manager=io_manager, max_concurrency=max_concurrency)
    return await executor.execute(plan)
