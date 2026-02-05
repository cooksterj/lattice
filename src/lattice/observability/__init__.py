"""
Lattice Observability Module.

This module provides enhanced execution with full observability:
- Log capture during execution
- Data lineage tracking (read/write events)
- Data quality checks on assets
- Persistent run history storage

Public API
----------
materialize_with_observability
    Enhanced materialize function with full observability.

Models
------
RunResult
    Extended execution result with logs, lineage, and checks.
RunRecord
    Flat structure for persistent storage.
CheckResult
    Result of a data quality check.
LogEntry
    A captured log entry.
LineageEvent
    A data lineage event (read/write).
CheckStatus
    Status enum for checks.

Checks
------
CheckDefinition
    Definition of a data quality check.
CheckRegistry
    Registry of checks.
AssetWithChecks
    Wrapper enabling .check decorator.
get_global_check_registry
    Get the global check registry.
run_check
    Run a single check on a value.

Lineage
-------
LineageTracker
    Tracks read/write events.
LineageIOManager
    IO manager wrapper that records lineage.

Log Capture
-----------
ExecutionLogHandler
    Logging handler that captures entries.
capture_logs
    Context manager for log capture.

History Storage
---------------
RunHistoryStore
    Abstract base for history storage.
SQLiteRunHistoryStore
    SQLite-backed storage implementation.
"""

import logging
from datetime import date

from lattice.executor import ExecutionResult, Executor
from lattice.io.base import IOManager
from lattice.io.memory import MemoryIOManager
from lattice.models import AssetKey
from lattice.observability.checks import (
    AssetWithChecks,
    CheckDefinition,
    CheckRegistry,
    get_global_check_registry,
    run_check,
)
from lattice.observability.history import RunHistoryStore, SQLiteRunHistoryStore
from lattice.observability.lineage import LineageIOManager, LineageTracker
from lattice.observability.log_capture import ExecutionLogHandler, capture_logs
from lattice.observability.models import (
    CheckResult,
    CheckStatus,
    LineageEvent,
    LogEntry,
    RunRecord,
    RunResult,
)
from lattice.plan import ExecutionPlan
from lattice.registry import AssetRegistry, get_global_registry

logger = logging.getLogger(__name__)

__all__ = [
    # Main function
    "materialize_with_observability",
    # Models
    "RunResult",
    "RunRecord",
    "CheckResult",
    "CheckStatus",
    "LogEntry",
    "LineageEvent",
    # Checks
    "CheckDefinition",
    "CheckRegistry",
    "AssetWithChecks",
    "get_global_check_registry",
    "run_check",
    # Lineage
    "LineageTracker",
    "LineageIOManager",
    # Log capture
    "ExecutionLogHandler",
    "capture_logs",
    # History
    "RunHistoryStore",
    "SQLiteRunHistoryStore",
]


def materialize_with_observability(
    registry: AssetRegistry | None = None,
    target: AssetKey | str | None = None,
    io_manager: IOManager | None = None,
    history_store: RunHistoryStore | None = None,
    check_registry: CheckRegistry | None = None,
    partition_key: date | None = None,
) -> RunResult:
    """
    Enhanced materialize with full observability.

    Executes assets with:
    - Log capture during execution
    - Lineage tracking (read/write events)
    - Data quality checks on completed assets
    - Optional persistent run history

    Parameters
    ----------
    registry : AssetRegistry or None
        Registry containing asset definitions.
        Defaults to the global registry.
    target : AssetKey or str or None
        Target asset to materialize (with dependencies).
        If None, materializes all assets.
    io_manager : IOManager or None
        Storage backend. Defaults to MemoryIOManager.
    history_store : RunHistoryStore or None
        Optional history store for persistence.
    check_registry : CheckRegistry or None
        Registry of checks to run. Defaults to global registry.
    partition_key : date or None
        Optional partition key for partitioned execution.

    Returns
    -------
    RunResult
        Extended result with logs, lineage, and check results.

    Examples
    --------
    >>> from lattice import asset
    >>> from lattice.observability import materialize_with_observability, SQLiteRunHistoryStore
    >>>
    >>> @asset
    ... def my_data() -> dict:
    ...     return {"value": 42}
    ...
    >>> @my_data.check
    ... def value_positive(data: dict) -> bool:
    ...     return data["value"] > 0
    ...
    >>> store = SQLiteRunHistoryStore(":memory:")
    >>> result = materialize_with_observability(history_store=store)
    >>> assert len(result.check_results) == 1
    >>> assert result.check_results[0].passed
    """
    if registry is None:
        registry = get_global_registry()

    if check_registry is None:
        check_registry = get_global_check_registry()

    # Set up IO manager with lineage tracking
    base_io_manager = io_manager if io_manager is not None else MemoryIOManager()
    lineage_tracker = LineageTracker()
    lineage_io_manager = LineageIOManager(base_io_manager, lineage_tracker)

    # Create execution plan
    plan = ExecutionPlan.resolve(registry, target=target)

    # Set up log capture with callbacks to track current asset
    log_handler: ExecutionLogHandler | None = None

    def on_asset_start(key: AssetKey) -> None:
        lineage_tracker.set_current_asset(key)
        if log_handler is not None:
            log_handler.set_current_asset(key)

    def on_asset_complete(result: ExecutionResult) -> None:
        pass  # We could do additional tracking here

    # Create executor with callbacks
    executor = Executor(
        io_manager=lineage_io_manager,
        on_asset_start=on_asset_start,
        partition_key=partition_key,
    )

    # Execute with log capture
    with capture_logs("lattice") as handler:
        log_handler = handler
        execution_result = executor.execute(plan)

    # Run checks on completed assets
    check_results: list[CheckResult] = []
    for asset_result in execution_result.asset_results:
        if asset_result.status.value == "completed":
            asset_key = asset_result.key
            checks = check_registry.get_checks(asset_key)
            for check_def in checks:
                try:
                    value = base_io_manager.load(asset_key)
                    check_result = run_check(check_def, value)
                    check_results.append(check_result)
                except Exception as e:
                    # If we can't load the asset, record an error
                    check_results.append(
                        CheckResult(
                            passed=False,
                            check_name=check_def.name,
                            asset_key=asset_key,
                            status=CheckStatus.ERROR,
                            error=f"Failed to load asset for check: {e}",
                        )
                    )

    # Build the run result
    run_result = RunResult(
        execution_result=execution_result,
        logs=tuple(handler.entries),
        lineage=tuple(lineage_tracker.events),
        check_results=tuple(check_results),
    )

    # Save to history store if provided
    if history_store is not None:
        target_str = str(target) if target is not None else None
        partition_str = partition_key.isoformat() if partition_key is not None else None
        record = RunRecord.from_run_result(
            run_result,
            target=target_str,
            partition_key=partition_str,
        )
        history_store.save(record)
        logger.info("Saved run record %s to history store", execution_result.run_id)

    return run_result
