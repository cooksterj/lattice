"""Pydantic schemas for execution API responses."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class AssetStatusSchema(BaseModel):
    """Status of a single asset during execution."""

    model_config = ConfigDict(frozen=True)

    id: str
    status: str  # "pending" | "running" | "completed" | "failed" | "skipped"
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None


class ExecutionStatusSchema(BaseModel):
    """Current execution state."""

    model_config = ConfigDict(frozen=True)

    is_running: bool
    run_id: str | None = None
    started_at: str | None = None
    current_asset: str | None = None
    total_assets: int = 0
    completed_count: int = 0
    failed_count: int = 0
    asset_statuses: list[AssetStatusSchema] = []


class MemorySnapshotSchema(BaseModel):
    """Memory usage snapshot."""

    model_config = ConfigDict(frozen=True)

    timestamp: str
    rss_mb: float  # Resident Set Size
    vms_mb: float  # Virtual Memory Size
    percent: float  # Percentage of total system memory


class ExecutionMemorySchema(BaseModel):
    """Memory usage during execution."""

    model_config = ConfigDict(frozen=True)

    current: MemorySnapshotSchema | None = None
    peak_rss_mb: float = 0.0
    timeline: list[MemorySnapshotSchema] = []


class ExecutionStartRequest(BaseModel):
    """Request to start execution."""

    model_config = ConfigDict(frozen=True)

    target: str | None = None
    include_downstream: bool = False
    execution_date: date | None = None
    execution_date_end: date | None = None


class ExecutionStartResponse(BaseModel):
    """Response after starting execution."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    message: str


class ExecutionStopResponse(BaseModel):
    """Response after requesting execution stop."""

    model_config = ConfigDict(frozen=True)

    success: bool
    message: str


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    model_config = ConfigDict(frozen=True)

    type: str  # "asset_start" | "asset_complete" | "memory_update" | "execution_complete"
    data: dict[str, Any]
