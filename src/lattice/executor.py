"""Executor for materializing assets.

This module provides the execution engine that walks an ExecutionPlan,
loads dependencies via IO managers, invokes asset functions, and stores
results. Includes both synchronous (Executor) and asynchronous (AsyncExecutor)
implementations.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from lattice.asset import SKIP_PARAMS
from lattice.graph import DependencyGraph
from lattice.io.base import IOManager
from lattice.io.memory import MemoryIOManager
from lattice.models import AssetDefinition, AssetKey
from lattice.plan import ExecutionPlan

logger = logging.getLogger(__name__)

# TYPE_CHECKING block for imports only needed by type checkers (mypy, pyright).
# AssetRegistry is imported here to avoid circular imports at runtime:
# registry.py imports from models.py, and this module uses AssetRegistry
# only in type annotations (not at runtime), so we defer the import.
if TYPE_CHECKING:
    from lattice.registry import AssetRegistry


class AssetStatus(str, Enum):
    """Status of an asset during execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AssetExecutionResult(BaseModel):
    """
    Result of executing a single asset.

    Attributes
    ----------
    key : AssetKey
        The asset that was executed.
    status : AssetStatus
        Final status of the execution.
    started_at : datetime or None
        When execution started.
    completed_at : datetime or None
        When execution completed.
    error : str or None
        Error message if execution failed.
    duration_ms : float or None
        Execution duration in milliseconds.
    """

    model_config = ConfigDict(frozen=True)

    key: AssetKey
    status: AssetStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    duration_ms: float | None = None


class ExecutionState(BaseModel):
    """
    Current state of an execution run.

    This model is mutable during execution to track progress.
    Use Executor.current_state to access during callbacks.

    Attributes
    ----------
    run_id : str
        Unique identifier for this execution run.
    started_at : datetime
        When the run started.
    completed_at : datetime or None
        When the run has completed.
    status : AssetStatus
        Current overall status.
    current_asset : AssetKey or None
        Currently executing asset.
    asset_results : dict
        Results for completed assets.
    total_assets : int
        Total number of assets in the plan.
    completed_count : int
        Number of successfully completed assets.
    failed_count : int
        Number of failed assets.
    """

    model_config = ConfigDict(frozen=False)

    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: AssetStatus = AssetStatus.PENDING
    current_asset: AssetKey | None = None
    asset_results: dict[str, AssetExecutionResult] = Field(default_factory=dict)
    total_assets: int = 0
    completed_count: int = 0
    failed_count: int = 0


class ExecutionResult(BaseModel):
    """
    Final result of an execution run.

    This is an immutable summary returned after execution completes.

    Attributes
    ----------
    run_id : str
        Unique identifier for this execution run.
    started_at : datetime
        When the run started.
    completed_at : datetime
        When the run completed.
    status : AssetStatus
        Final status (COMPLETED or FAILED).
    asset_results : tuple of AssetExecutionResult
        Results for each asset in execution order.
    total_assets : int
        Total number of assets in the plan.
    completed_count : int
        Number of successfully completed assets.
    failed_count : int
        Number of failed assets.
    duration_ms : float
        Total execution duration in milliseconds.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    started_at: datetime
    completed_at: datetime
    status: AssetStatus
    asset_results: tuple[AssetExecutionResult, ...]
    total_assets: int
    completed_count: int
    failed_count: int
    duration_ms: float


class Executor:
    """
    Executes an asset materialization plan.

    Walks the ExecutionPlan in topological order, loading dependencies
    from the IO manager and storing results.

    Parameters
    ----------
    io_manager : IOManager, optional
        Storage backend for loading/storing assets.
        Defaults to MemoryIOManager.
    on_asset_start : callable, optional
        Callback when asset execution starts.
        Signature: fn(key: AssetKey) -> None
    on_asset_complete : callable, optional
        Callback when asset execution completes.
        Signature: fn(result: AssetExecutionResult) -> None
    partition_key : date, optional
        Date partition key to inject into asset functions that accept it.
    """

    def __init__(
        self,
        io_manager: IOManager | None = None,
        on_asset_start: Callable[[AssetKey], None] | None = None,
        on_asset_complete: Callable[[AssetExecutionResult], None] | None = None,
        partition_key: date | None = None,
    ) -> None:
        """Initialize executor with IO manager and optional callbacks."""
        self.io_manager = io_manager if io_manager is not None else MemoryIOManager()
        self.on_asset_start = on_asset_start
        self.on_asset_complete = on_asset_complete
        self._partition_key = partition_key
        self._current_state: ExecutionState | None = None

    @property
    def current_state(self) -> ExecutionState | None:
        """
        Get the current execution state.

        Returns None when not executing. During execution, returns
        a mutable ExecutionState with current progress.

        Returns
        -------
        ExecutionState or None
            Current state if executing, None otherwise.
        """
        return self._current_state

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """
        Execute a materialization plan.

        Executes assets in topological order. If an asset fails,
        all downstream assets are skipped.

        Parameters
        ----------
        plan : ExecutionPlan
            The plan to execute.

        Returns
        -------
        ExecutionResult
            Summary of the execution run.
        """
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()

        logger.info("Starting execution run %s with %d assets", run_id, len(plan))

        # Initialize state
        self._current_state = ExecutionState(
            run_id=run_id,
            started_at=started_at,
            total_assets=len(plan),
        )

        results: list[AssetExecutionResult] = []
        failed = False

        try:
            for asset_def in plan:
                if failed:
                    # Skip remaining assets after failure
                    result = AssetExecutionResult(
                        key=asset_def.key,
                        status=AssetStatus.SKIPPED,
                    )
                    logger.debug("Skipping asset %s due to prior failure", asset_def.key)
                else:
                    result = self._execute_asset(asset_def)

                    if result.status == AssetStatus.FAILED:
                        failed = True
                        self._current_state.failed_count += 1
                    elif result.status == AssetStatus.COMPLETED:
                        self._current_state.completed_count += 1

                results.append(result)
                self._current_state.asset_results[str(asset_def.key)] = result

                if self.on_asset_complete:
                    self.on_asset_complete(result)

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            self._current_state.completed_at = completed_at
            self._current_state.status = AssetStatus.FAILED if failed else AssetStatus.COMPLETED

            logger.info(
                "Execution run %s completed: status=%s, duration=%.2fms, completed=%d, failed=%d",
                run_id,
                self._current_state.status.value,
                duration_ms,
                self._current_state.completed_count,
                self._current_state.failed_count,
            )

            return ExecutionResult(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status=self._current_state.status,
                asset_results=tuple(results),
                total_assets=len(plan),
                completed_count=self._current_state.completed_count,
                failed_count=self._current_state.failed_count,
                duration_ms=duration_ms,
            )

        finally:
            self._current_state = None

    def _execute_asset(self, asset_def: AssetDefinition) -> AssetExecutionResult:
        """
        Execute a single asset.

        Parameters
        ----------
        asset_def : AssetDefinition
            The asset to execute.

        Returns
        -------
        AssetExecutionResult
            Result of the execution.
        """
        key = asset_def.key
        started_at = datetime.now()

        logger.info("Executing asset: %s", key)
        logger.debug(
            "Asset %s has %d dependencies: %s",
            key,
            len(asset_def.dependencies),
            [str(d) for d in asset_def.dependencies],
        )

        # Update state
        if self._current_state:
            self._current_state.current_asset = key

        if self.on_asset_start:
            self.on_asset_start(key)

        try:
            # Derive parameter names from function signature and zip with deps
            sig = inspect.signature(asset_def.fn)
            param_names = [p for p in sig.parameters if p not in SKIP_PARAMS]
            kwargs: dict[str, Any] = {}
            for param_name, dep_key in zip(param_names, asset_def.dependencies, strict=True):
                kwargs[param_name] = self.io_manager.load(dep_key)

            # Inject partition_key if asset accepts it
            if self._partition_key is not None and "partition_key" in sig.parameters:
                kwargs["partition_key"] = self._partition_key

            # Execute asset function
            result_value = asset_def.fn(**kwargs)

            # Store result
            self.io_manager.store(key, result_value)

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            logger.info("Asset %s completed in %.2fms", key, duration_ms)

            return AssetExecutionResult(
                key=key,
                status=AssetStatus.COMPLETED,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

        except Exception as e:
            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            logger.error("Asset %s failed: %s", key, e, exc_info=True)

            return AssetExecutionResult(
                key=key,
                status=AssetStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                error=str(e),
                duration_ms=duration_ms,
            )


class AsyncExecutor:
    """
    Asynchronous executor for parallel asset materialization.

    Executes independent assets concurrently within each DAG level.
    Supports both sync and async asset functions.

    Parameters
    ----------
    io_manager : IOManager, optional
        Storage backend for loading/storing assets.
        Defaults to MemoryIOManager.
    max_concurrency : int, optional
        Maximum number of assets to execute in parallel.
        Defaults to 4.
    on_asset_start : callable, optional
        Callback when asset execution starts. Can be sync or async.
        Signature: fn(key: AssetKey) -> None or Coroutine
    on_asset_complete : callable, optional
        Callback when asset execution completes. Can be sync or async.
        Signature: fn(result: AssetExecutionResult) -> None or Coroutine
    partition_key : date, optional
        Date partition key to inject into asset functions that accept it.
    """

    def __init__(
        self,
        io_manager: IOManager | None = None,
        max_concurrency: int = 4,
        on_asset_start: Callable[[AssetKey], Any] | None = None,
        on_asset_complete: Callable[[AssetExecutionResult], Any] | None = None,
        partition_key: date | None = None,
    ) -> None:
        """Initialize async executor with IO manager and concurrency settings."""
        self.io_manager = io_manager if io_manager is not None else MemoryIOManager()
        self.max_concurrency = max_concurrency
        self.on_asset_start = on_asset_start
        self.on_asset_complete = on_asset_complete
        self._partition_key = partition_key
        self._current_state: ExecutionState | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._cancelled = False

    @property
    def current_state(self) -> ExecutionState | None:
        """
        Get the current execution state.

        Returns None when not executing. During execution, returns
        a mutable ExecutionState with current progress.

        Returns
        -------
        ExecutionState or None
            Current state if executing, None otherwise.
        """
        return self._current_state

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """
        Execute a materialization plan with parallel execution.

        Assets at the same dependency level are executed concurrently,
        respecting the max_concurrency limit.

        Parameters
        ----------
        plan : ExecutionPlan
            The plan to execute.

        Returns
        -------
        ExecutionResult
            Summary of the execution run.
        """
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()
        self._cancelled = False

        logger.info(
            "Starting async execution run %s with %d assets (max_concurrency=%d)",
            run_id,
            len(plan),
            self.max_concurrency,
        )

        # Initialize state
        self._current_state = ExecutionState(
            run_id=run_id,
            started_at=started_at,
            total_assets=len(plan),
        )

        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        results: list[AssetExecutionResult] = []
        failed_keys: set[AssetKey] = set()

        # Build a map of key -> AssetDefinition for quick lookup
        asset_map: dict[AssetKey, AssetDefinition] = {
            asset_def.key: asset_def for asset_def in plan
        }

        # Get execution levels from the graph
        from lattice.registry import AssetRegistry

        temp_registry = AssetRegistry()
        for asset_def in plan:
            temp_registry.register(asset_def)

        graph = DependencyGraph.from_registry(temp_registry)
        levels = graph.get_execution_levels(list(asset_map.keys()))
        logger.debug("Execution plan has %d levels", len(levels))

        try:
            for level in levels:
                if self._cancelled:
                    break

                # Filter out assets whose dependencies have failed
                runnable: list[AssetKey] = []
                for key in level:
                    asset_def = asset_map[key]
                    deps_failed = any(dep in failed_keys for dep in asset_def.dependencies)
                    if deps_failed:
                        # Skip this asset
                        result = AssetExecutionResult(
                            key=key,
                            status=AssetStatus.SKIPPED,
                        )
                        results.append(result)
                        self._current_state.asset_results[str(key)] = result
                        failed_keys.add(key)
                        if self.on_asset_complete:
                            cb_result = self.on_asset_complete(result)
                            if inspect.iscoroutine(cb_result):
                                await cb_result
                    else:
                        runnable.append(key)

                if not runnable:
                    continue

                # Execute all runnable assets in this level concurrently
                level_results = await self._execute_level([asset_map[k] for k in runnable])

                for result in level_results:
                    results.append(result)
                    self._current_state.asset_results[str(result.key)] = result

                    if result.status == AssetStatus.FAILED:
                        failed_keys.add(result.key)
                        self._current_state.failed_count += 1
                    elif result.status == AssetStatus.COMPLETED:
                        self._current_state.completed_count += 1

                    if self.on_asset_complete:
                        cb_result = self.on_asset_complete(result)
                        if inspect.iscoroutine(cb_result):
                            await cb_result

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            self._current_state.completed_at = completed_at
            self._current_state.status = (
                AssetStatus.FAILED if failed_keys else AssetStatus.COMPLETED
            )

            logger.info(
                "Async execution run %s completed: status=%s, "
                "duration=%.2fms, completed=%d, failed=%d",
                run_id,
                self._current_state.status.value,
                duration_ms,
                self._current_state.completed_count,
                self._current_state.failed_count,
            )

            return ExecutionResult(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status=self._current_state.status,
                asset_results=tuple(results),
                total_assets=len(plan),
                completed_count=self._current_state.completed_count,
                failed_count=self._current_state.failed_count,
                duration_ms=duration_ms,
            )

        finally:
            self._current_state = None
            self._semaphore = None

    async def _execute_level(self, assets: list[AssetDefinition]) -> list[AssetExecutionResult]:
        """
        Execute all assets in a level concurrently.

        Parameters
        ----------
        assets : list of AssetDefinition
            Assets to execute in parallel.

        Returns
        -------
        list of AssetExecutionResult
            Results for each asset.
        """
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self._execute_asset(a)) for a in assets]

        return [task.result() for task in tasks]

    async def _execute_asset(self, asset_def: AssetDefinition) -> AssetExecutionResult:
        """
        Execute a single asset with semaphore-controlled concurrency.

        Parameters
        ----------
        asset_def : AssetDefinition
            The asset to execute.

        Returns
        -------
        AssetExecutionResult
            Result of the execution.
        """
        assert self._semaphore is not None

        async with self._semaphore:
            if self._cancelled:
                logger.debug("Asset %s skipped due to cancellation", asset_def.key)
                return AssetExecutionResult(
                    key=asset_def.key,
                    status=AssetStatus.SKIPPED,
                )

            key = asset_def.key
            started_at = datetime.now()

            logger.info("Executing asset: %s", key)
            logger.debug(
                "Asset %s has %d dependencies: %s",
                key,
                len(asset_def.dependencies),
                [str(d) for d in asset_def.dependencies],
            )

            # Update state
            if self._current_state:
                self._current_state.current_asset = key

            if self.on_asset_start:
                result = self.on_asset_start(key)
                if inspect.iscoroutine(result):
                    await result

            try:
                # Derive parameter names from function signature and zip with deps
                sig = inspect.signature(asset_def.fn)
                param_names = [p for p in sig.parameters if p not in SKIP_PARAMS]
                kwargs: dict[str, Any] = {}
                for param_name, dep_key in zip(param_names, asset_def.dependencies, strict=True):
                    kwargs[param_name] = self.io_manager.load(dep_key)

                # Inject partition_key if asset accepts it
                if self._partition_key is not None and "partition_key" in sig.parameters:
                    kwargs["partition_key"] = self._partition_key

                # Execute asset function (handle both sync and async)
                if inspect.iscoroutinefunction(asset_def.fn):
                    result_value = await asset_def.fn(**kwargs)
                else:
                    # Run sync function in thread pool to avoid blocking
                    result_value = await asyncio.to_thread(asset_def.fn, **kwargs)

                # Store result
                self.io_manager.store(key, result_value)

                completed_at = datetime.now()
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                logger.info("Asset %s completed in %.2fms", key, duration_ms)

                return AssetExecutionResult(
                    key=key,
                    status=AssetStatus.COMPLETED,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                )

            except Exception as e:
                completed_at = datetime.now()
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                logger.error("Asset %s failed: %s", key, e, exc_info=True)

                return AssetExecutionResult(
                    key=key,
                    status=AssetStatus.FAILED,
                    started_at=started_at,
                    completed_at=completed_at,
                    error=str(e),
                    duration_ms=duration_ms,
                )

    def cancel(self) -> None:
        """
        Request cancellation of the current execution.

        Running assets will complete, but no new assets will start.
        """
        self._cancelled = True


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
    from lattice.registry import get_global_registry

    if registry is None:
        registry = get_global_registry()

    plan = ExecutionPlan.resolve(registry, target=target)
    executor = AsyncExecutor(io_manager=io_manager, max_concurrency=max_concurrency)
    return await executor.execute(plan)
