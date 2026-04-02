"""Asynchronous executor for parallel asset materialization.

This module provides the async execution engine that runs independent
assets concurrently within each DAG level, respecting a configurable
concurrency limit via semaphore.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from lattice.asset import SKIP_PARAMS
from lattice.executor.models import (
    AssetExecutionResult,
    AssetStatus,
    ExecutionResult,
    ExecutionState,
)
from lattice.graph import DependencyGraph
from lattice.io.base import IOManager
from lattice.io.memory import MemoryIOManager
from lattice.models import AssetDefinition, AssetKey
from lattice.plan import ExecutionPlan

logger = logging.getLogger(__name__)


def _build_asset_map(plan: ExecutionPlan) -> dict[AssetKey, AssetDefinition]:
    """
    Build a mapping from AssetKey to AssetDefinition.

    Parameters
    ----------
    plan : ExecutionPlan
        The execution plan containing asset definitions.

    Returns
    -------
    dict of AssetKey to AssetDefinition
        Lookup map for quick asset access.
    """
    return {asset_def.key: asset_def for asset_def in plan}


def _build_execution_levels(
    plan: ExecutionPlan,
    asset_map: dict[AssetKey, AssetDefinition],
) -> list[list[AssetKey]]:
    """
    Compute topological execution levels from the plan.

    Parameters
    ----------
    plan : ExecutionPlan
        The execution plan containing asset definitions.
    asset_map : dict of AssetKey to AssetDefinition
        Lookup map from key to definition.

    Returns
    -------
    list of list of AssetKey
        Asset keys grouped by execution level.
    """
    from lattice.registry import AssetRegistry

    temp_registry = AssetRegistry()
    for asset_def in plan:
        temp_registry.register(asset_def)

    graph = DependencyGraph.from_registry(temp_registry)
    return graph.get_execution_levels(list(asset_map.keys()))


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

        asset_map = _build_asset_map(plan)
        levels = _build_execution_levels(plan, asset_map)
        logger.debug("Execution plan has %d levels", len(levels))

        try:
            for level in levels:
                if self._cancelled:
                    break

                runnable, skipped = await self._partition_level(
                    level,
                    asset_map,
                    failed_keys,
                )
                results.extend(skipped)
                failed_keys.update(r.key for r in skipped)

                if not runnable:
                    continue

                level_results = await self._execute_level(
                    [asset_map[k] for k in runnable],
                )
                await self._record_results(level_results, results, failed_keys)

            return self._finalize_run(run_id, started_at, results, failed_keys)

        finally:
            self._current_state = None
            self._semaphore = None

    async def _invoke_complete_callback(
        self,
        result: AssetExecutionResult,
    ) -> None:
        """
        Invoke the on_asset_complete callback if registered.

        Handles both sync and async callbacks transparently.

        Parameters
        ----------
        result : AssetExecutionResult
            The result to pass to the callback.
        """
        if not self.on_asset_complete:
            return
        cb_result = self.on_asset_complete(result)
        if inspect.iscoroutine(cb_result):
            await cb_result

    async def _partition_level(
        self,
        level: list[AssetKey],
        asset_map: dict[AssetKey, AssetDefinition],
        failed_keys: set[AssetKey],
    ) -> tuple[list[AssetKey], list[AssetExecutionResult]]:
        """
        Split a level into runnable keys and skipped results.

        Assets whose dependencies have failed are skipped. Their
        results are recorded in the current execution state and
        the on_asset_complete callback is invoked.

        Parameters
        ----------
        level : list of AssetKey
            All asset keys in this execution level.
        asset_map : dict
            Mapping from AssetKey to AssetDefinition.
        failed_keys : set of AssetKey
            Keys of assets that have already failed or been skipped.

        Returns
        -------
        tuple of (list of AssetKey, list of AssetExecutionResult)
            Runnable keys and skip results for assets with failed deps.
        """
        runnable: list[AssetKey] = []
        skipped: list[AssetExecutionResult] = []

        for key in level:
            asset_def = asset_map[key]
            deps_failed = any(dep in failed_keys for dep in asset_def.dependencies)
            if not deps_failed:
                runnable.append(key)
                continue

            result = AssetExecutionResult(key=key, status=AssetStatus.SKIPPED)
            skipped.append(result)
            assert self._current_state is not None
            self._current_state.asset_results[str(key)] = result
            await self._invoke_complete_callback(result)

        return runnable, skipped

    async def _record_results(
        self,
        level_results: list[AssetExecutionResult],
        results: list[AssetExecutionResult],
        failed_keys: set[AssetKey],
    ) -> None:
        """
        Record execution results and update run state.

        Parameters
        ----------
        level_results : list of AssetExecutionResult
            Results from executing a single level.
        results : list of AssetExecutionResult
            Accumulator for all results in the run (mutated in place).
        failed_keys : set of AssetKey
            Keys of failed/skipped assets (mutated in place).
        """
        assert self._current_state is not None

        for result in level_results:
            results.append(result)
            self._current_state.asset_results[str(result.key)] = result

            if result.status == AssetStatus.FAILED:
                failed_keys.add(result.key)
                self._current_state.failed_count += 1
            elif result.status == AssetStatus.COMPLETED:
                self._current_state.completed_count += 1

            await self._invoke_complete_callback(result)

    def _finalize_run(
        self,
        run_id: str,
        started_at: datetime,
        results: list[AssetExecutionResult],
        failed_keys: set[AssetKey],
    ) -> ExecutionResult:
        """
        Build the final ExecutionResult and log completion.

        Parameters
        ----------
        run_id : str
            Identifier for this execution run.
        started_at : datetime
            When the run started.
        results : list of AssetExecutionResult
            All individual asset results.
        failed_keys : set of AssetKey
            Keys of assets that failed or were skipped.

        Returns
        -------
        ExecutionResult
            Summary of the completed run.
        """
        assert self._current_state is not None

        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        self._current_state.completed_at = completed_at
        self._current_state.status = AssetStatus.FAILED if failed_keys else AssetStatus.COMPLETED

        logger.info(
            "Async execution run %s completed: status=%s, duration=%.2fms, completed=%d, failed=%d",
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
            total_assets=self._current_state.total_assets,
            completed_count=self._current_state.completed_count,
            failed_count=self._current_state.failed_count,
            duration_ms=duration_ms,
        )

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
