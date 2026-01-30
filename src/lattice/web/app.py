"""FastAPI application factory for Lattice web visualization."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lattice.registry import AssetRegistry, get_global_registry
from lattice.web.routes import create_router

# Paths relative to this file
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def create_app(registry: AssetRegistry | None = None) -> FastAPI:
    """
    Create a FastAPI application for visualizing the asset graph.

    Parameters
    ----------
    registry : AssetRegistry or None
        The asset registry to visualize. Defaults to global registry.

    Returns
    -------
    FastAPI
        Configured FastAPI application.
    """
    if registry is None:
        registry = get_global_registry()

    app = FastAPI(
        title="Lattice",
        description="Asset dependency graph visualization",
        version="0.2.0",
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Configure templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Add routes
    router = create_router(registry, templates)
    app.include_router(router)

    return app


def serve(
    registry: AssetRegistry | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """
    Start the visualization server.

    Parameters
    ----------
    registry : AssetRegistry or None
        The asset registry to visualize. Defaults to global registry.
    host : str
        Host to bind to. Defaults to localhost.
    port : int
        Port to listen on. Defaults to 8000.
    """
    import uvicorn

    app = create_app(registry)
    uvicorn.run(app, host=host, port=port)
