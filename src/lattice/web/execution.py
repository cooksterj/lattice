"""Execution API routes and state management."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect

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

# TYPE_CHECKING is False at runtime but True during static analysis.
# These imports are deferred to avoid circular dependencies between the web
# module and the executor module, while still providing type hints.
# - Executor: Used for type annotations on the _executor property
# - AssetExecutionResult: Used in the _broadcast_asset_complete callback signature
if TYPE_CHECKING:
    from lattice.executor import AssetExecutionResult, Executor


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

    def __init__(self) -> None:
        """Initialize with an empty state."""
        self._executor: Executor | None = None
        self._is_running: bool = False
        self._websockets: set[WebSocket] = set()
        self._memory_timeline: list[MemorySnapshotSchema] = []
        self._peak_rss_mb: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        """Check if an execution is currently in progress."""
        return self._is_running

    @property
    def executor(self) -> Executor | None:
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
        self._loop = None

    def add_websocket(self, ws: WebSocket) -> None:
        """Register a WebSocket client."""
        self._websockets.add(ws)

    def remove_websocket(self, ws: WebSocket) -> None:
        """Unregister a WebSocket client."""
        self._websockets.discard(ws)

    def record_memory_snapshot(self, snapshot: MemorySnapshotSchema) -> None:
        """Record a memory snapshot and update the peak if needed."""
        self._memory_timeline.append(snapshot)
        if snapshot.rss_mb > self._peak_rss_mb:
            self._peak_rss_mb = snapshot.rss_mb

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected WebSocket clients."""
        dead_sockets: set[WebSocket] = set()
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)
        self._websockets -= dead_sockets

    def _broadcast_asset_start(self, key: AssetKey) -> None:
        """Callback for when an asset starts execution (called from executor thread)."""
        if self._loop is None:
            return

        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(
                self.broadcast({"type": "asset_start", "data": {"asset_id": str(key)}})
            )
        )

    def _broadcast_asset_complete(self, result: AssetExecutionResult) -> None:
        """Callback for when an asset completes execution (called from executor thread)."""
        if self._loop is None:
            return

        message: dict[str, Any] = {
            "type": "asset_complete",
            "data": {
                "asset_id": str(result.key),
                "status": result.status.value,
                "duration_ms": result.duration_ms,
                "error": result.error,
            },
        }

        def _schedule_broadcast(msg: dict[str, Any] = message) -> None:
            asyncio.create_task(self.broadcast(msg))

        self._loop.call_soon_threadsafe(_schedule_broadcast)

    async def run_execution(self, registry: AssetRegistry, target: str | None) -> None:
        """
        Run the asset materialization.

        Parameters
        ----------
        registry : AssetRegistry
            The registry containing asset definitions.
        target : str or None
            Optional target asset to materialize.
        """
        from lattice.executor import Executor
        from lattice.io.memory import MemoryIOManager

        try:
            plan = ExecutionPlan.resolve(registry, target=target)
            io_manager = MemoryIOManager()

            self._loop = asyncio.get_running_loop()
            self._memory_timeline = []
            self._peak_rss_mb = 0.0
            self._is_running = True

            executor = Executor(
                io_manager=io_manager,
                on_asset_start=self._broadcast_asset_start,
                on_asset_complete=self._broadcast_asset_complete,
            )
            self._executor = executor

            result = await self._loop.run_in_executor(None, executor.execute, plan)

            await self.broadcast(
                {
                    "type": "execution_complete",
                    "data": {
                        "run_id": result.run_id,
                        "status": result.status.value,
                        "duration_ms": result.duration_ms,
                        "completed_count": result.completed_count,
                        "failed_count": result.failed_count,
                    },
                }
            )

        finally:
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
                completed_at=result.completed_at.isoformat() if result.completed_at else None,
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

        background_tasks.add_task(manager.run_execution, registry, request.target)

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
