"""Executor package for materializing assets.

This package provides the execution engine that walks an ExecutionPlan,
loads dependencies via IO managers, invokes asset functions, and stores
results. Includes both synchronous (Executor) and asynchronous (AsyncExecutor)
implementations.

Submodules
----------
models
    Data models for execution state and results.
sync
    Synchronous Executor implementation.
async_executor
    Asynchronous AsyncExecutor with parallel execution.
materialize
    Top-level materialize() and materialize_async() helpers.
"""

from lattice.executor.async_executor import AsyncExecutor
from lattice.executor.materialize import materialize, materialize_async
from lattice.executor.models import (
    AssetExecutionResult,
    AssetStatus,
    ExecutionResult,
    ExecutionState,
)
from lattice.executor.sync import Executor

__all__ = [
    "AssetExecutionResult",
    "AssetStatus",
    "AsyncExecutor",
    "ExecutionResult",
    "ExecutionState",
    "Executor",
    "materialize",
    "materialize_async",
]
