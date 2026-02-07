"""API routes for run history visualization."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from lattice.observability.history import RunHistoryStore


class RunSummarySchema(BaseModel):
    """Summary of a single run."""

    run_id: str
    started_at: str
    completed_at: str
    status: str
    duration_ms: float
    total_assets: int
    completed_count: int
    failed_count: int
    target: str | None = None
    partition_key: str | None = None


class RunDetailSchema(RunSummarySchema):
    """Detailed run information including logs, checks, lineage."""

    logs: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    check_results: list[dict[str, Any]] = []
    asset_results: list[dict[str, Any]] = []


class RunListSchema(BaseModel):
    """List of runs with pagination info."""

    runs: list[RunSummarySchema]
    total: int
    limit: int
    offset: int


class AssetSummarySchema(BaseModel):
    """Summary statistics for an asset."""

    asset_key: str
    total_runs: int
    passed_count: int
    failed_count: int
    last_run_at: str | None = None
    avg_duration_ms: float | None = None


class PartitionSummarySchema(BaseModel):
    """Summary statistics for a partition/date."""

    partition_key: str
    total_runs: int
    completed_count: int
    failed_count: int
    total_duration_ms: float


class AssetRunSchema(BaseModel):
    """A single run's data filtered to a specific asset."""

    run_id: str
    started_at: str
    completed_at: str
    partition_key: str | None = None
    asset_status: str
    asset_duration_ms: float | None = None
    checks_passed: int = 0
    checks_total: int = 0


class AssetHistorySchema(BaseModel):
    """Run history filtered to a specific asset."""

    asset_key: str
    total_runs: int
    passed_count: int
    failed_count: int
    avg_duration_ms: float | None = None
    runs: list[AssetRunSchema]


class HistorySummarySchema(BaseModel):
    """Summary of run history by asset and partition."""

    asset_summaries: list[AssetSummarySchema]
    partition_summaries: list[PartitionSummarySchema]
    total_runs: int
    total_passed: int
    total_failed: int


def create_history_router(
    history_store: RunHistoryStore | None,
    templates: Jinja2Templates,
) -> APIRouter:
    """
    Create an API router for run history endpoints.

    Parameters
    ----------
    history_store : RunHistoryStore or None
        The history store to query. If None, endpoints return empty results.
    templates : Jinja2Templates
        Jinja2 templates for HTML responses.

    Returns
    -------
    APIRouter
        Configured FastAPI router.
    """
    router = APIRouter()

    @router.get("/history", response_class=HTMLResponse)
    async def history_page(request: Request) -> HTMLResponse:
        """Serve the run history page."""
        return templates.TemplateResponse(request, "history.html")

    @router.get("/api/history/runs", response_model=RunListSchema)
    async def list_runs(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(default=None),
    ) -> RunListSchema:
        """List runs with optional filtering and pagination."""
        if history_store is None:
            return RunListSchema(runs=[], total=0, limit=limit, offset=offset)

        runs = history_store.list_runs(limit=limit, status=status, offset=offset)
        total = history_store.count(status=status)

        run_summaries = [
            RunSummarySchema(
                run_id=r.run_id,
                started_at=r.started_at.isoformat(),
                completed_at=r.completed_at.isoformat(),
                status=r.status,
                duration_ms=r.duration_ms,
                total_assets=r.total_assets,
                completed_count=r.completed_count,
                failed_count=r.failed_count,
                target=r.target,
                partition_key=r.partition_key,
            )
            for r in runs
        ]

        return RunListSchema(
            runs=run_summaries,
            total=total,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/history/runs/{run_id}", response_model=RunDetailSchema)
    async def get_run(run_id: str) -> RunDetailSchema:
        """Get detailed information about a specific run."""
        if history_store is None:
            raise HTTPException(status_code=404, detail="History store not configured")

        record = history_store.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        return RunDetailSchema(
            run_id=record.run_id,
            started_at=record.started_at.isoformat(),
            completed_at=record.completed_at.isoformat(),
            status=record.status,
            duration_ms=record.duration_ms,
            total_assets=record.total_assets,
            completed_count=record.completed_count,
            failed_count=record.failed_count,
            target=record.target,
            partition_key=record.partition_key,
            logs=json.loads(record.logs_json),
            lineage=json.loads(record.lineage_json),
            check_results=json.loads(record.check_results_json),
            asset_results=json.loads(record.asset_results_json),
        )

    @router.get("/api/history/summary", response_model=HistorySummarySchema)
    async def get_summary(
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> HistorySummarySchema:
        """Get summary of run history by asset and partition."""
        if history_store is None:
            return HistorySummarySchema(
                asset_summaries=[],
                partition_summaries=[],
                total_runs=0,
                total_passed=0,
                total_failed=0,
            )

        runs = history_store.list_runs(limit=limit)

        # Aggregate by asset
        asset_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_runs": 0,
                "passed_count": 0,
                "failed_count": 0,
                "last_run_at": None,
                "total_duration_ms": 0,
            }
        )

        # Aggregate by partition
        partition_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_runs": 0,
                "completed_count": 0,
                "failed_count": 0,
                "total_duration_ms": 0,
            }
        )

        total_passed = 0
        total_failed = 0

        for run in runs:
            # Count run status
            if run.status == "completed":
                total_passed += 1
            elif run.status == "failed":
                total_failed += 1

            # Parse asset results
            asset_results = json.loads(run.asset_results_json)
            for ar in asset_results:
                asset_key = ar["key"]
                stats = asset_stats[asset_key]
                stats["total_runs"] += 1
                if ar["status"] == "completed":
                    stats["passed_count"] += 1
                elif ar["status"] == "failed":
                    stats["failed_count"] += 1
                if ar.get("duration_ms"):
                    stats["total_duration_ms"] += ar["duration_ms"]
                # Track last run time
                if stats["last_run_at"] is None:
                    stats["last_run_at"] = run.started_at.isoformat()

            # Aggregate by partition
            partition_key = run.partition_key or run.started_at.strftime("%Y-%m-%d")
            pstats = partition_stats[partition_key]
            pstats["total_runs"] += 1
            if run.status == "completed":
                pstats["completed_count"] += 1
            elif run.status == "failed":
                pstats["failed_count"] += 1
            pstats["total_duration_ms"] += run.duration_ms

        # Build summaries
        asset_summaries = [
            AssetSummarySchema(
                asset_key=key,
                total_runs=stats["total_runs"],
                passed_count=stats["passed_count"],
                failed_count=stats["failed_count"],
                last_run_at=stats["last_run_at"],
                avg_duration_ms=(
                    stats["total_duration_ms"] / stats["total_runs"]
                    if stats["total_runs"] > 0
                    else None
                ),
            )
            for key, stats in sorted(asset_stats.items())
        ]

        partition_summaries = [
            PartitionSummarySchema(
                partition_key=key,
                total_runs=stats["total_runs"],
                completed_count=stats["completed_count"],
                failed_count=stats["failed_count"],
                total_duration_ms=stats["total_duration_ms"],
            )
            for key, stats in sorted(partition_stats.items(), reverse=True)
        ]

        return HistorySummarySchema(
            asset_summaries=asset_summaries,
            partition_summaries=partition_summaries[:7],  # Last 7 partitions
            total_runs=len(runs),
            total_passed=total_passed,
            total_failed=total_failed,
        )

    @router.get("/api/history/assets/{key:path}", response_model=AssetHistorySchema)
    async def get_asset_history(key: str) -> AssetHistorySchema:
        """Get run history filtered to a specific asset."""
        if history_store is None:
            return AssetHistorySchema(
                asset_key=key,
                total_runs=0,
                passed_count=0,
                failed_count=0,
                avg_duration_ms=None,
                runs=[],
            )

        all_runs = history_store.list_runs(limit=500)

        asset_runs: list[AssetRunSchema] = []
        passed = 0
        failed = 0
        total_duration = 0.0
        duration_count = 0

        for run in all_runs:
            asset_results = json.loads(run.asset_results_json)
            check_results = json.loads(run.check_results_json)

            # Find this asset in the run's results
            asset_result = None
            for ar in asset_results:
                if ar["key"] == key:
                    asset_result = ar
                    break

            if asset_result is None:
                continue

            # Count checks for this asset
            asset_checks = [c for c in check_results if c.get("asset_key") == key]
            checks_passed = sum(1 for c in asset_checks if c.get("passed"))
            checks_total = len(asset_checks)

            # Track stats
            asset_status = asset_result.get("status", "unknown")
            if asset_status == "completed":
                passed += 1
            elif asset_status == "failed":
                failed += 1

            duration_ms = asset_result.get("duration_ms")
            if duration_ms is not None:
                total_duration += duration_ms
                duration_count += 1

            asset_runs.append(
                AssetRunSchema(
                    run_id=run.run_id,
                    started_at=run.started_at.isoformat(),
                    completed_at=run.completed_at.isoformat(),
                    partition_key=run.partition_key,
                    asset_status=asset_status,
                    asset_duration_ms=duration_ms,
                    checks_passed=checks_passed,
                    checks_total=checks_total,
                )
            )

        avg_duration = total_duration / duration_count if duration_count > 0 else None

        return AssetHistorySchema(
            asset_key=key,
            total_runs=len(asset_runs),
            passed_count=passed,
            failed_count=failed,
            avg_duration_ms=avg_duration,
            runs=asset_runs,
        )

    @router.delete("/api/history/runs/{run_id}")
    async def delete_run(run_id: str) -> dict[str, bool]:
        """Delete a run record."""
        if history_store is None:
            raise HTTPException(status_code=404, detail="History store not configured")

        deleted = history_store.delete(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        return {"deleted": True}

    return router
