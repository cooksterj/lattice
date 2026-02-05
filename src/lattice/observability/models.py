"""
Core data models for Lattice observability.

This module defines models for tracking execution runs with full observability:
log capture, lineage tracking, and data quality checks.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lattice.executor import ExecutionResult
from lattice.models import AssetKey


class CheckStatus(str, Enum):
    """Status of a data quality check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class CheckResult(BaseModel):
    """
    Result of running a data quality check on an asset.

    Attributes
    ----------
    passed : bool
        Whether the check passed.
    check_name : str
        Name of the check that was run.
    asset_key : AssetKey
        The asset that was checked.
    status : CheckStatus
        Detailed status of the check execution.
    metadata : dict
        Additional metadata about the check result.
    duration_ms : float or None
        How long the check took to run in milliseconds.
    error : str or None
        Error message if the check errored.
    """

    model_config = ConfigDict(frozen=True)

    passed: bool
    check_name: str
    asset_key: AssetKey
    status: CheckStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    error: str | None = None


class LogEntry(BaseModel):
    """
    A captured log entry during execution.

    Attributes
    ----------
    timestamp : datetime
        When the log entry was created.
    level : str
        Log level (DEBUG, INFO, WARNING, ERROR, etc.).
    logger_name : str
        Name of the logger that produced this entry.
    message : str
        The log message.
    asset_key : AssetKey or None
        The asset being executed when this log was produced, if any.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    level: str
    logger_name: str
    message: str
    asset_key: AssetKey | None = None


class LineageEvent(BaseModel):
    """
    A data lineage event tracking asset reads and writes.

    Attributes
    ----------
    event_type : str
        Either "read" or "write".
    asset_key : AssetKey
        The asset that was read or written.
    timestamp : datetime
        When the event occurred.
    source_asset : AssetKey or None
        For reads, the asset that triggered the read.
    metadata : dict
        Additional metadata about the event.
    """

    model_config = ConfigDict(frozen=True)

    event_type: Literal["read", "write"]
    asset_key: AssetKey
    timestamp: datetime
    source_asset: AssetKey | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    """
    Extended execution result with logs, lineage, and check results.

    This wraps an ExecutionResult with additional observability data
    collected during the run.

    Attributes
    ----------
    execution_result : ExecutionResult
        The underlying execution result.
    logs : tuple of LogEntry
        Log entries captured during execution.
    lineage : tuple of LineageEvent
        Lineage events (reads/writes) during execution.
    check_results : tuple of CheckResult
        Results of data quality checks run on assets.
    """

    model_config = ConfigDict(frozen=True)

    execution_result: ExecutionResult
    logs: tuple[LogEntry, ...] = ()
    lineage: tuple[LineageEvent, ...] = ()
    check_results: tuple[CheckResult, ...] = ()

    @property
    def run_id(self) -> str:
        """Get the run ID from the underlying execution result."""
        return self.execution_result.run_id

    @property
    def status(self) -> str:
        """Get the status from the underlying execution result."""
        return self.execution_result.status.value

    @property
    def success(self) -> bool:
        """Check if the run completed successfully."""
        return self.execution_result.failed_count == 0


class RunRecord(BaseModel):
    """
    Flat structure for SQLite storage of run history.

    Complex data (logs, lineage, checks) is stored as JSON strings
    for easy SQLite persistence.

    Attributes
    ----------
    run_id : str
        Unique identifier for this execution run.
    started_at : datetime
        When the run started.
    completed_at : datetime
        When the run completed.
    status : str
        Final status (completed, failed).
    duration_ms : float
        Total execution duration in milliseconds.
    total_assets : int
        Total number of assets in the plan.
    completed_count : int
        Number of successfully completed assets.
    failed_count : int
        Number of failed assets.
    target : str or None
        Target asset key if a specific target was requested.
    partition_key : str or None
        Partition key if partitioned execution.
    logs_json : str
        JSON-serialized log entries.
    lineage_json : str
        JSON-serialized lineage events.
    check_results_json : str
        JSON-serialized check results.
    asset_results_json : str
        JSON-serialized asset execution results.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    started_at: datetime
    completed_at: datetime
    status: str
    duration_ms: float
    total_assets: int
    completed_count: int
    failed_count: int
    target: str | None = None
    partition_key: str | None = None
    logs_json: str = "[]"
    lineage_json: str = "[]"
    check_results_json: str = "[]"
    asset_results_json: str = "[]"

    @classmethod
    def from_run_result(
        cls,
        result: RunResult,
        target: str | None = None,
        partition_key: str | None = None,
    ) -> "RunRecord":
        """
        Create a RunRecord from a RunResult.

        Parameters
        ----------
        result : RunResult
            The run result to convert.
        target : str or None
            Target asset key if specified.
        partition_key : str or None
            Partition key if partitioned.

        Returns
        -------
        RunRecord
            Flattened record for storage.
        """
        import json

        exec_result = result.execution_result

        # Serialize logs
        logs_data = [
            {
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
                "logger_name": log.logger_name,
                "message": log.message,
                "asset_key": str(log.asset_key) if log.asset_key else None,
            }
            for log in result.logs
        ]

        # Serialize lineage
        lineage_data = [
            {
                "event_type": event.event_type,
                "asset_key": str(event.asset_key),
                "timestamp": event.timestamp.isoformat(),
                "source_asset": str(event.source_asset) if event.source_asset else None,
                "metadata": event.metadata,
            }
            for event in result.lineage
        ]

        # Serialize check results
        checks_data = [
            {
                "passed": check.passed,
                "check_name": check.check_name,
                "asset_key": str(check.asset_key),
                "status": check.status.value,
                "metadata": check.metadata,
                "duration_ms": check.duration_ms,
                "error": check.error,
            }
            for check in result.check_results
        ]

        # Serialize asset results
        asset_results_data = [
            {
                "key": str(ar.key),
                "status": ar.status.value,
                "started_at": ar.started_at.isoformat() if ar.started_at else None,
                "completed_at": ar.completed_at.isoformat() if ar.completed_at else None,
                "error": ar.error,
                "duration_ms": ar.duration_ms,
            }
            for ar in exec_result.asset_results
        ]

        return cls(
            run_id=exec_result.run_id,
            started_at=exec_result.started_at,
            completed_at=exec_result.completed_at,
            status=exec_result.status.value,
            duration_ms=exec_result.duration_ms,
            total_assets=exec_result.total_assets,
            completed_count=exec_result.completed_count,
            failed_count=exec_result.failed_count,
            target=target,
            partition_key=partition_key,
            logs_json=json.dumps(logs_data),
            lineage_json=json.dumps(lineage_data),
            check_results_json=json.dumps(checks_data),
            asset_results_json=json.dumps(asset_results_data),
        )
