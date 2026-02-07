"""Execution API routes and state management."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)

from lattice.models import AssetKey
from lattice.plan import ExecutionPlan
from lattice.registry import AssetRegistry
from lattice.web.schemas_execution import (
    AssetStatusSchema,
    ExecutionMemorySchema,
    ExecutionStartRequest,
    ExecutionStartResponse,
    ExecutionStatusSchema,
    MemorySnapshotSchema,
)

logger = logging.getLogger(__name__)

# Observability imports - for tracking lineage, logs, checks, and history
if TYPE_CHECKING:
    from lattice.observability import CheckRegistry, RunHistoryStore

# TYPE_CHECKING is False at runtime but True during static analysis.
# These imports are deferred to avoid circular dependencies between the web
# module and the executor module, while still providing type hints.
# - AsyncExecutor: Used for type annotations on the _executor property
# - AssetExecutionResult: Used in the _broadcast_asset_complete callback signature
if TYPE_CHECKING:
    from lattice.executor import AssetExecutionResult, AsyncExecutor


def get_memory_snapshot() -> MemorySnapshotSchema:
    """Get current process memory usage."""
    try:
        import psutil  # type: ignore[import-untyped]

        process = psutil.Process()
        mem_info = process.memory_info()
        return MemorySnapshotSchema(
            timestamp=datetime.now().isoformat(),
            rss_mb=mem_info.rss / (1024 * 1024),
            vms_mb=mem_info.vms / (1024 * 1024),
            percent=process.memory_percent(),
        )
    except ImportError:
        return MemorySnapshotSchema(
            timestamp=datetime.now().isoformat(),
            rss_mb=0.0,
            vms_mb=0.0,
            percent=0.0,
        )


class ExecutionManager:
    """
    Manages execution state for the web service.

    Handles tracking of running executions, connected WebSocket clients,
    and memory usage metrics. Designed for single-server deployment.
    """

    REPLAY_BUFFER_SIZE: int = 500

    def __init__(
        self,
        max_concurrency: int = 4,
        history_store: RunHistoryStore | None = None,
        check_registry: CheckRegistry | None = None,
    ) -> None:
        """Initialize with an empty state."""
        self._executor: AsyncExecutor | None = None
        self._is_running: bool = False
        self._websockets: set[WebSocket] = set()
        self._memory_timeline: list[MemorySnapshotSchema] = []
        self._peak_rss_mb: float = 0.0
        self._max_concurrency = max_concurrency
        self._history_store = history_store
        self._check_registry = check_registry
        self._asset_subscribers: dict[str, set[WebSocket]] = {}
        self._replay_buffers: dict[str, deque[dict[str, Any]]] = {}
        self._log_queue: asyncio.Queue[Any] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        """Check if an execution is currently in progress."""
        return self._is_running

    @property
    def executor(self) -> AsyncExecutor | None:
        """Get the current executor, if any."""
        return self._executor

    @property
    def peak_rss_mb(self) -> float:
        """Get peak RSS memory usage in MB."""
        return self._peak_rss_mb

    @property
    def memory_timeline(self) -> list[MemorySnapshotSchema]:
        """Get the memory usage timeline (last 100 snapshots)."""
        return self._memory_timeline[-100:]

    def stop_execution(self) -> None:
        """Mark execution as stopped."""
        self._is_running = False
        self._executor = None

    def add_websocket(self, ws: WebSocket) -> None:
        """Register a WebSocket client."""
        self._websockets.add(ws)
        logger.debug("WebSocket client connected, total: %d", len(self._websockets))

    def remove_websocket(self, ws: WebSocket) -> None:
        """Unregister a WebSocket client."""
        self._websockets.discard(ws)
        logger.debug("WebSocket client disconnected, total: %d", len(self._websockets))

    def record_memory_snapshot(self, snapshot: MemorySnapshotSchema) -> None:
        """Record a memory snapshot and update the peak if needed."""
        self._memory_timeline.append(snapshot)
        if snapshot.rss_mb > self._peak_rss_mb:
            self._peak_rss_mb = snapshot.rss_mb

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected WebSocket clients."""
        logger.debug(
            "Broadcasting message type=%s to %d clients",
            message.get("type"),
            len(self._websockets),
        )
        dead_sockets: set[WebSocket] = set()
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)
        if dead_sockets:
            logger.debug("Removed %d dead WebSocket connections", len(dead_sockets))
        self._websockets -= dead_sockets

    def add_asset_subscriber(self, asset_key: str, ws: WebSocket) -> None:
        """Register a WebSocket subscriber for a specific asset."""
        if asset_key not in self._asset_subscribers:
            self._asset_subscribers[asset_key] = set()
        self._asset_subscribers[asset_key].add(ws)
        logger.debug(
            "Asset subscriber added for %s, total: %d",
            asset_key,
            len(self._asset_subscribers[asset_key]),
        )

    def remove_asset_subscriber(self, asset_key: str, ws: WebSocket) -> None:
        """Unregister a WebSocket subscriber for a specific asset."""
        if asset_key in self._asset_subscribers:
            self._asset_subscribers[asset_key].discard(ws)
            if not self._asset_subscribers[asset_key]:
                del self._asset_subscribers[asset_key]
            logger.debug("Asset subscriber removed for %s", asset_key)

    async def broadcast_to_asset(self, asset_key: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all subscribers of a specific asset."""
        subscribers = set(self._asset_subscribers.get(asset_key, ()))
        dead_sockets: set[WebSocket] = set()
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)
        if dead_sockets and asset_key in self._asset_subscribers:
            self._asset_subscribers[asset_key] -= dead_sockets

    def get_replay_buffer(self, asset_key: str) -> list[dict[str, Any]]:
        """Get the replay buffer contents for an asset."""
        return list(self._replay_buffers.get(asset_key, deque()))

    def _on_log_entry_sync(self, entry: Any) -> None:
        """Synchronous callback invoked by ExecutionLogHandler.emit().

        Safe to call from any thread. Enqueues the entry onto the
        asyncio event loop for async processing via call_soon_threadsafe.
        """
        if self._log_queue is None or self._loop is None:
            return
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._log_queue.put_nowait, entry)

    async def _drain_log_queue(self) -> None:
        """Async task that drains the log queue and routes entries to subscribers."""
        assert self._log_queue is not None
        while True:
            entry = await self._log_queue.get()
            if entry is None:
                break  # Sentinel to stop draining
            await self._route_log_entry(entry)

    async def _route_log_entry(self, entry: Any) -> None:
        """Route a log entry to the correct asset's subscribers and replay buffer."""
        asset_key = getattr(entry, "asset_key", None)
        if asset_key is None:
            return
        asset_key_str = str(asset_key)
        message: dict[str, Any] = {
            "type": "asset_log",
            "data": {
                "asset_key": asset_key_str,
                "level": entry.level,
                "message": entry.message,
                "timestamp": entry.timestamp.isoformat(),
                "logger_name": entry.logger_name,
            },
        }
        # Store in replay buffer
        if asset_key_str not in self._replay_buffers:
            self._replay_buffers[asset_key_str] = deque(maxlen=self.REPLAY_BUFFER_SIZE)
        self._replay_buffers[asset_key_str].append(message)
        # Send to subscribers
        await self.broadcast_to_asset(asset_key_str, message)

    async def _broadcast_asset_start(self, key: AssetKey) -> None:
        """Callback for when an asset starts execution."""
        await self.broadcast({"type": "asset_start", "data": {"asset_id": str(key)}})

    async def _broadcast_asset_complete(self, result: AssetExecutionResult) -> None:
        """Callback for when an asset completes execution."""
        message: dict[str, Any] = {
            "type": "asset_complete",
            "data": {
                "asset_id": str(result.key),
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "error": result.error,
            },
        }
        await self.broadcast(message)
        await self.broadcast_to_asset(str(result.key), message)

    async def run_execution(
        self,
        registry: AssetRegistry,
        target: str | None,
        include_downstream: bool = False,
        execution_date: date | None = None,
        execution_date_end: date | None = None,
    ) -> None:
        """
        Run the asset materialization with parallel execution.

        Parameters
        ----------
        registry : AssetRegistry
            The registry containing asset definitions.
        target : str or None
            Optional target asset to materialize.
        include_downstream : bool
            If True, execute target and downstream dependents instead of
            target and upstream dependencies.
        execution_date : date or None
            Optional start date for partition key. If provided, assets that
            accept a partition_key parameter will receive this date.
        execution_date_end : date or None
            Optional end date for date range execution. If provided along with
            execution_date, the pipeline will be executed sequentially for each
            date in the range.
        """
        from lattice.executor import AsyncExecutor
        from lattice.io.memory import MemoryIOManager
        from lattice.observability import (
            CheckResult,
            CheckStatus,
            ExecutionLogHandler,
            LineageIOManager,
            LineageTracker,
            RunRecord,
            RunResult,
            capture_logs,
            get_global_check_registry,
            run_check,
        )

        # Build list of dates to execute
        dates_to_execute: list[date] = []
        if execution_date is not None:
            if execution_date_end is not None and execution_date_end > execution_date:
                # Generate date range
                current = execution_date
                while current <= execution_date_end:
                    dates_to_execute.append(current)
                    current += timedelta(days=1)
            else:
                # Single date
                dates_to_execute.append(execution_date)

        logger.info(
            "Web execution starting: target=%s, include_downstream=%s, dates=%s",
            target or "all",
            include_downstream,
            [str(d) for d in dates_to_execute] if dates_to_execute else "none",
        )

        # Get check registry (use provided or global)
        check_registry = (
            self._check_registry
            if self._check_registry is not None
            else get_global_check_registry()
        )

        try:
            plan = ExecutionPlan.resolve(
                registry, target=target, include_downstream=include_downstream
            )

            self._memory_timeline = []
            self._peak_rss_mb = 0.0
            self._is_running = True

            # Set up async log streaming bridge
            self._log_queue = asyncio.Queue()
            self._replay_buffers = {}  # Clear for new execution
            self._loop = asyncio.get_running_loop()
            self._drain_task = asyncio.create_task(self._drain_log_queue())

            total_dates = len(dates_to_execute) if dates_to_execute else 1
            total_completed = 0
            total_failed = 0
            overall_start = datetime.now()

            # Execute for each date (or once if no dates specified)
            execution_dates: list[date | None] = (
                list(dates_to_execute) if dates_to_execute else [None]
            )

            for date_index, partition_date in enumerate(execution_dates):
                if partition_date is not None:
                    # Broadcast partition start
                    await self.broadcast(
                        {
                            "type": "partition_start",
                            "data": {
                                "current_date": partition_date.isoformat(),
                                "current_date_index": date_index + 1,
                                "total_dates": total_dates,
                            },
                        }
                    )

                # Set up observability components
                base_io_manager = MemoryIOManager()
                lineage_tracker = LineageTracker()
                io_manager = LineageIOManager(base_io_manager, lineage_tracker)

                partition_start = datetime.now()

                # Execute with log capture — handler must exist before
                # the callback is defined so it can be bound via default arg
                with capture_logs("lattice", on_entry=self._on_log_entry_sync) as log_handler:
                    # Create callbacks that update observability context
                    # Use default argument to bind at definition time (avoids B023)
                    async def on_asset_start_with_tracking(
                        key: AssetKey,
                        tracker: LineageTracker = lineage_tracker,
                        handler: ExecutionLogHandler = log_handler,
                    ) -> None:
                        tracker.set_current_asset(key)
                        handler.set_current_asset(key)
                        await self._broadcast_asset_start(key)
                        await self.broadcast_to_asset(
                            str(key),
                            {
                                "type": "asset_start",
                                "data": {"asset_key": str(key)},
                            },
                        )

                    executor = AsyncExecutor(
                        io_manager=io_manager,
                        max_concurrency=self._max_concurrency,
                        on_asset_start=on_asset_start_with_tracking,
                        on_asset_complete=self._broadcast_asset_complete,
                        partition_key=partition_date,
                    )
                    self._executor = executor

                    result = await executor.execute(plan)

                partition_duration = (datetime.now() - partition_start).total_seconds() * 1000

                # Run checks on completed assets
                check_results: list[CheckResult] = []
                for asset_result in result.asset_results:
                    if asset_result.status.value == "completed":
                        asset_key = asset_result.key
                        checks = check_registry.get_checks(asset_key)
                        for check_def in checks:
                            try:
                                value: Any = base_io_manager.load(asset_key)
                                check_result = run_check(check_def, value)
                                check_results.append(check_result)
                            except Exception as e:
                                check_results.append(
                                    CheckResult(
                                        passed=False,
                                        check_name=check_def.name,
                                        asset_key=asset_key,
                                        status=CheckStatus.ERROR,
                                        error=f"Failed to load asset for check: {e}",
                                    )
                                )

                # Broadcast check results
                if check_results:
                    checks_passed = sum(1 for c in check_results if c.passed)
                    checks_failed = len(check_results) - checks_passed
                    await self.broadcast(
                        {
                            "type": "checks_complete",
                            "data": {
                                "total": len(check_results),
                                "passed": checks_passed,
                                "failed": checks_failed,
                                "results": [
                                    {
                                        "check_name": c.check_name,
                                        "asset_key": str(c.asset_key),
                                        "passed": c.passed,
                                        "status": c.status.value,
                                        "error": c.error,
                                    }
                                    for c in check_results
                                ],
                            },
                        }
                    )

                # Build RunResult and save to history store
                if self._history_store is not None:
                    run_result = RunResult(
                        execution_result=result,
                        logs=tuple(log_handler.entries),
                        lineage=tuple(lineage_tracker.events),
                        check_results=tuple(check_results),
                    )
                    target_str = target if target is not None else None
                    partition_str = (
                        partition_date.isoformat() if partition_date is not None else None
                    )
                    record = RunRecord.from_run_result(
                        run_result,
                        target=target_str,
                        partition_key=partition_str,
                    )
                    self._history_store.save(record)
                    logger.info("Saved run record %s to history store", result.run_id)

                total_completed += result.completed_count
                total_failed += result.failed_count

                if partition_date is not None:
                    # Broadcast partition complete
                    await self.broadcast(
                        {
                            "type": "partition_complete",
                            "data": {
                                "date": partition_date.isoformat(),
                                "status": result.status.value,
                                "duration_ms": partition_duration,
                                "completed_count": result.completed_count,
                                "failed_count": result.failed_count,
                            },
                        }
                    )

                logger.info(
                    "Partition execution completed: date=%s, status=%s, duration=%.2fms",
                    partition_date.isoformat() if partition_date else "none",
                    result.status.value,
                    partition_duration,
                )

            overall_duration = (datetime.now() - overall_start).total_seconds() * 1000

            logger.info(
                "Web execution completed: total_dates=%d, duration=%.2fms, completed=%d, failed=%d",
                total_dates,
                overall_duration,
                total_completed,
                total_failed,
            )

            await self.broadcast(
                {
                    "type": "execution_complete",
                    "data": {
                        "run_id": result.run_id if dates_to_execute else result.run_id,
                        "status": "failed" if total_failed > 0 else "completed",
                        "duration_ms": overall_duration,
                        "completed_count": total_completed,
                        "failed_count": total_failed,
                        "total_dates": total_dates,
                    },
                }
            )

        finally:
            # Shut down async log streaming bridge
            # Yield to let pending call_soon_threadsafe callbacks execute
            # before sending the sentinel, so all log entries are drained.
            await asyncio.sleep(0)
            if self._log_queue is not None:
                self._log_queue.put_nowait(None)  # Sentinel to stop drain task
            if self._drain_task is not None:
                await self._drain_task
            self._log_queue = None
            self._drain_task = None
            self._loop = None
            self.stop_execution()


def create_execution_router(
    registry: AssetRegistry,
    manager: ExecutionManager,
) -> APIRouter:
    """
    Create an API router for execution endpoints.

    Parameters
    ----------
    registry : AssetRegistry
        The asset registry for resolving execution plans.
    manager : ExecutionManager
        The execution state manager.

    Returns
    -------
    APIRouter
        Configured FastAPI router for execution endpoints.
    """
    router = APIRouter(prefix="/api/execution", tags=["execution"])

    @router.get("/status", response_model=ExecutionStatusSchema)
    async def get_execution_status() -> ExecutionStatusSchema:
        """Get current execution status."""
        if not manager.is_running or manager.executor is None:
            return ExecutionStatusSchema(is_running=False)

        state = manager.executor.current_state
        if state is None:
            return ExecutionStatusSchema(is_running=False)

        asset_statuses = [
            AssetStatusSchema(
                id=str(key),
                status=result.status.value,
                started_at=result.started_at.isoformat() if result.started_at else None,
                completed_at=(result.completed_at.isoformat() if result.completed_at else None),
                duration_ms=result.duration_ms,
                error=result.error,
            )
            for key, result in state.asset_results.items()
        ]

        return ExecutionStatusSchema(
            is_running=True,
            run_id=state.run_id,
            started_at=state.started_at.isoformat(),
            current_asset=str(state.current_asset) if state.current_asset else None,
            total_assets=state.total_assets,
            completed_count=state.completed_count,
            failed_count=state.failed_count,
            asset_statuses=asset_statuses,
        )

    @router.get("/memory", response_model=ExecutionMemorySchema)
    async def get_execution_memory() -> ExecutionMemorySchema:
        """Get memory usage during execution."""
        current = get_memory_snapshot()
        manager.record_memory_snapshot(current)

        return ExecutionMemorySchema(
            current=current,
            peak_rss_mb=manager.peak_rss_mb,
            timeline=list(manager.memory_timeline),
        )

    @router.post("/start", response_model=ExecutionStartResponse)
    async def start_execution(
        request: ExecutionStartRequest,
        background_tasks: BackgroundTasks,
    ) -> ExecutionStartResponse:
        """Start asset materialization."""
        if manager.is_running:
            raise HTTPException(status_code=409, detail="Execution already in progress")

        background_tasks.add_task(
            manager.run_execution,
            registry,
            request.target,
            request.include_downstream,
            request.execution_date,
            request.execution_date_end,
        )

        return ExecutionStartResponse(
            run_id="starting",
            message="Execution started",
        )

    return router


def create_websocket_router(manager: ExecutionManager) -> APIRouter:
    """
    Create a router for the execution WebSocket endpoint.

    Parameters
    ----------
    manager : ExecutionManager
        The execution state manager.

    Returns
    -------
    APIRouter
        Router with WebSocket endpoint.
    """
    router = APIRouter()

    @router.websocket("/ws/execution")
    async def execution_websocket(websocket: WebSocket) -> None:
        """WebSocket for real-time execution updates."""
        await websocket.accept()
        manager.add_websocket(websocket)

        try:
            while True:
                if manager.is_running:
                    snapshot = get_memory_snapshot()
                    manager.record_memory_snapshot(snapshot)

                    try:
                        await websocket.send_json(
                            {"type": "memory_update", "data": snapshot.model_dump()}
                        )
                    except RuntimeError:
                        break

                await asyncio.sleep(0.5)

        except WebSocketDisconnect:
            pass
        finally:
            manager.remove_websocket(websocket)

    return router


def create_asset_websocket_router(manager: ExecutionManager) -> APIRouter:
    """
    Create a router for per-asset WebSocket endpoints.

    Parameters
    ----------
    manager : ExecutionManager
        The execution state manager.

    Returns
    -------
    APIRouter
        Router with asset-scoped WebSocket endpoint.
    """
    router = APIRouter()

    @router.websocket("/ws/asset/{key:path}")
    async def asset_websocket(websocket: WebSocket, key: str) -> None:
        """WebSocket for per-asset real-time log streaming."""
        await websocket.accept()
        manager.add_asset_subscriber(key, websocket)

        try:
            # Send replay buffer catch-up
            replay = manager.get_replay_buffer(key)
            if replay:
                await websocket.send_json(
                    {
                        "type": "replay",
                        "data": {"entries": replay},
                    }
                )

            # Keep-alive loop — detects disconnects
            while True:
                await websocket.receive_text()

        except WebSocketDisconnect:
            pass
        finally:
            manager.remove_asset_subscriber(key, websocket)

    return router
