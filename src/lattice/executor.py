"""Executor for materializing assets.

This module provides the execution engine that walks an ExecutionPlan,
loads dependencies via IO managers, invokes asset functions, and stores
results.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from lattice.io.base import IOManager
from lattice.io.memory import MemoryIOManager
from lattice.models import AssetDefinition, AssetKey
from lattice.plan import ExecutionPlan

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
    """

    def __init__(
        self,
        io_manager: IOManager | None = None,
        on_asset_start: Callable[[AssetKey], None] | None = None,
        on_asset_complete: Callable[[AssetExecutionResult], None] | None = None,
    ) -> None:
        """Initialize executor with IO manager and optional callbacks."""
        self.io_manager = io_manager if io_manager is not None else MemoryIOManager()
        self.on_asset_start = on_asset_start
        self.on_asset_complete = on_asset_complete
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

        # Update state
        if self._current_state:
            self._current_state.current_asset = key

        if self.on_asset_start:
            self.on_asset_start(key)

        try:
            # Load dependencies using parameter names
            kwargs: dict[str, Any] = {}
            for param_name, dep_key in zip(
                asset_def.dependency_params, asset_def.dependencies, strict=True
            ):
                kwargs[param_name] = self.io_manager.load(dep_key)

            # Execute asset function
            result_value = asset_def.fn(**kwargs)

            # Store result
            self.io_manager.store(key, result_value)

            completed_at = datetime.now()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

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

            return AssetExecutionResult(
                key=key,
                status=AssetStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                error=str(e),
                duration_ms=duration_ms,
            )


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
