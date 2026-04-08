"""Synchronous executor for materializing assets.

This module provides the synchronous execution engine that walks an
ExecutionPlan in topological order, loading dependencies via IO managers,
invoking asset functions, and storing results.
"""

from __future__ import annotations

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
from lattice.io.base import IOManager
from lattice.io.memory import MemoryIOManager
from lattice.models import AssetDefinition, AssetKey
from lattice.plan import ExecutionPlan

logger = logging.getLogger(__name__)


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
    def _partition_key_str(self) -> str | None:
        """Return partition key as ISO string, or None."""
        return self._partition_key.isoformat() if self._partition_key else None

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
                result = self._execute_or_skip(asset_def, failed)
                failed = failed or result.status == AssetStatus.FAILED
                self._record_result(result)
                results.append(result)

            return self._finalize_run(run_id, started_at, results, failed)

        finally:
            self._current_state = None

    def _execute_or_skip(
        self,
        asset_def: AssetDefinition,
        failed: bool,
    ) -> AssetExecutionResult:
        """
        Execute an asset or skip it if a prior asset has failed.

        Parameters
        ----------
        asset_def : AssetDefinition
            The asset to execute.
        failed : bool
            Whether a prior asset in the plan has failed.

        Returns
        -------
        AssetExecutionResult
            Result of the execution or a skip result.
        """
        if failed:
            logger.debug("Skipping asset %s due to prior failure", asset_def.key)
            return AssetExecutionResult(
                key=asset_def.key,
                status=AssetStatus.SKIPPED,
            )
        return self._execute_asset(asset_def)

    def _record_result(self, result: AssetExecutionResult) -> None:
        """
        Record a single asset result into execution state and invoke callback.

        Parameters
        ----------
        result : AssetExecutionResult
            The result to record.
        """
        assert self._current_state is not None

        if result.status == AssetStatus.FAILED:
            self._current_state.failed_count += 1
        elif result.status == AssetStatus.COMPLETED:
            self._current_state.completed_count += 1

        self._current_state.asset_results[str(result.key)] = result

        if self.on_asset_complete:
            self.on_asset_complete(result)

    def _finalize_run(
        self,
        run_id: str,
        started_at: datetime,
        results: list[AssetExecutionResult],
        failed: bool,
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
        failed : bool
            Whether any asset in the run failed.

        Returns
        -------
        ExecutionResult
            Summary of the completed run.
        """
        assert self._current_state is not None

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
            total_assets=self._current_state.total_assets,
            completed_count=self._current_state.completed_count,
            failed_count=self._current_state.failed_count,
            duration_ms=duration_ms,
        )

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
                kwargs[param_name] = self.io_manager.load(
                    dep_key, partition_key=self._partition_key_str
                )

            # Inject partition_key if asset accepts it
            if self._partition_key is not None and "partition_key" in sig.parameters:
                kwargs["partition_key"] = self._partition_key

            # Execute asset function
            result_value = asset_def.fn(**kwargs)

            # Store result
            self.io_manager.store(key, result_value, partition_key=self._partition_key_str)

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
