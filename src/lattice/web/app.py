"""FastAPI application factory for Lattice web visualization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lattice.registry import AssetRegistry, get_global_registry
from lattice.web.execution_manager import ExecutionManager
from lattice.web.routes import create_router
from lattice.web.routes_execution import (
    create_asset_websocket_router,
    create_execution_router,
    create_websocket_router,
)
from lattice.web.routes_history import create_history_router

# TYPE_CHECKING block for imports only needed by type checkers (mypy, pyright).
# RunHistoryStore is imported here to avoid pulling in the full observability
# stack (SQLite, history models) at app-module load time. It is used only in
# the ``create_app`` function's type annotation for the optional history_store
# parameter.
if TYPE_CHECKING:
    from lattice.observability.history import RunHistoryStore

logger = logging.getLogger(__name__)

# Paths relative to this file
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def create_app(
    registry: AssetRegistry | None = None,
    history_store: RunHistoryStore | None = None,
) -> FastAPI:
    """
    Create a FastAPI application for visualizing the asset graph.

    Parameters
    ----------
    registry : AssetRegistry or None
        The asset registry to visualize. Defaults to global registry.
    history_store : RunHistoryStore or None
        Optional history store for run history visualization.

    Returns
    -------
    FastAPI
        Configured FastAPI application.
    """
    if registry is None:
        registry = get_global_registry()

    logger.info("Creating Lattice web application")

    app = FastAPI(
        title="Lattice",
        description="Asset dependency graph visualization",
        version="0.2.0",
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Configure templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Create a shared execution manager with history store for observability
    execution_manager = ExecutionManager(history_store=history_store)

    # Add graph/asset routes
    graph_router = create_router(registry, templates)
    app.include_router(graph_router)

    # Add execution routes
    execution_router = create_execution_router(registry, execution_manager)
    app.include_router(execution_router)

    # Add a WebSocket route (separate router for a path without /api prefix)
    ws_router = create_websocket_router(execution_manager)
    app.include_router(ws_router)

    # Add asset-scoped WebSocket route
    asset_ws_router = create_asset_websocket_router(execution_manager)
    app.include_router(asset_ws_router)

    # Add history routes
    history_router = create_history_router(history_store, templates)
    app.include_router(history_router)

    return app


def serve(
    registry: AssetRegistry | None = None,
    host: str | None = None,
    port: int | None = None,
    history_store: RunHistoryStore | None = None,
) -> None:
    """
    Start the visualization server.

    Parameters
    ----------
    registry : AssetRegistry or None
        The asset registry to visualize. Defaults to global registry.
    host : str or None
        Host to bind to. When *None*, reads ``LATTICE_HOST`` env var
        (default ``127.0.0.1``).
    port : int or None
        Port to listen on. When *None*, reads ``LATTICE_PORT`` env var
        (default ``8000``).
    history_store : RunHistoryStore or None
        Optional history store for run history visualization.
    """
    import uvicorn

    from lattice.config import get_host, get_port

    resolved_host = host if host is not None else get_host()
    resolved_port = port if port is not None else get_port()

    logger.info("Starting Lattice web server on %s:%d", resolved_host, resolved_port)

    app = create_app(registry, history_store=history_store)
    uvicorn.run(app, host=resolved_host, port=resolved_port)
