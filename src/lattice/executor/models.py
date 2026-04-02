"""Data models for asset execution.

This module defines the Pydantic models used to track execution state
and results: status enums, per-asset results, mutable execution state,
and immutable execution summaries.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from lattice.models import AssetKey


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
