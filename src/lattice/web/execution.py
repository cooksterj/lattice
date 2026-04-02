"""Backward-compatible re-exports for web execution module.

This module re-exports symbols from their new locations for backward
compatibility. New code should import directly from:

- ``lattice.web.execution_manager`` for ExecutionManager and get_memory_snapshot
- ``lattice.web.routes_execution`` for router factory functions
"""

from lattice.web.execution_manager import ExecutionManager, get_memory_snapshot
from lattice.web.routes_execution import (
    create_asset_websocket_router,
    create_execution_router,
    create_websocket_router,
)

__all__ = [
    "ExecutionManager",
    "create_asset_websocket_router",
    "create_execution_router",
    "create_websocket_router",
    "get_memory_snapshot",
]
