"""Execution API routes and WebSocket endpoints.

This module provides FastAPI router factories for execution control,
status polling, memory monitoring, and real-time WebSocket streaming.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)

from lattice.registry import AssetRegistry
from lattice.web.execution_manager import ExecutionManager, get_memory_snapshot
from lattice.web.schemas_execution import (
    AssetStatusSchema,
    ExecutionMemorySchema,
    ExecutionStartRequest,
    ExecutionStartResponse,
    ExecutionStatusSchema,
    ExecutionStopResponse,
)

logger = logging.getLogger(__name__)


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

    @router.post("/stop", response_model=ExecutionStopResponse)
    async def stop_execution() -> ExecutionStopResponse:
        """Stop the current execution.

        Running assets will complete, but no new assets will start.
        """
        if manager.cancel_execution():
            await manager.broadcast(
                {"type": "execution_cancelled", "data": {"message": "Execution stop requested"}}
            )
            return ExecutionStopResponse(success=True, message="Execution stop requested")
        return ExecutionStopResponse(success=False, message="No execution running")

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
