"""API routes for graph and asset visualization."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from lattice import __version__
from lattice.graph import DependencyGraph
from lattice.models import AssetKey
from lattice.observability import get_global_check_registry
from lattice.plan import ExecutionPlan
from lattice.registry import AssetRegistry
from lattice.web.schemas import (
    AssetDetailSchema,
    CheckSchema,
    EdgeSchema,
    GraphSchema,
    HealthSchema,
    NodeSchema,
    PlanSchema,
    PlanStepSchema,
)


def create_router(registry: AssetRegistry, templates: Jinja2Templates) -> APIRouter:
    """
    Create an API router for graph and asset endpoints.

    Parameters
    ----------
    registry : AssetRegistry
        The asset registry to serve.
    templates : Jinja2Templates
        Jinja2 templates for HTML responses.

    Returns
    -------
    APIRouter
        Configured FastAPI router.
    """
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Serve the main visualization page."""
        return templates.TemplateResponse(request, "index.html")

    @router.get("/api/graph", response_model=GraphSchema)
    async def get_graph() -> GraphSchema:
        """Get graph data for D3.js visualization."""
        graph = DependencyGraph.from_registry(registry)
        check_registry = get_global_check_registry()

        nodes: list[NodeSchema] = []
        edges: list[EdgeSchema] = []

        for asset_def in registry:
            key = asset_def.key
            node_id = str(key)

            # Get return type as string
            return_type = None
            if asset_def.return_type is not None:
                return_type = getattr(asset_def.return_type, "__name__", str(asset_def.return_type))

            # Get checks registered for this asset
            asset_checks = check_registry.get_checks(key)
            checks = [
                CheckSchema(name=check.name, description=check.description)
                for check in asset_checks
            ]

            nodes.append(
                NodeSchema(
                    id=node_id,
                    name=key.name,
                    group=key.group,
                    description=asset_def.description,
                    return_type=return_type,
                    dependency_count=len(asset_def.dependencies),
                    dependent_count=len(graph.reverse_adjacency.get(key, ())),
                    checks=checks,
                )
            )

            # Add edges for dependencies
            for dep in asset_def.dependencies:
                if dep in registry:
                    edges.append(EdgeSchema(source=str(dep), target=node_id))

        return GraphSchema(nodes=nodes, edges=edges)

    @router.get("/api/assets/{key:path}", response_model=AssetDetailSchema)
    async def get_asset(key: str) -> AssetDetailSchema:
        """Get detailed information about an asset."""
        # Parse the key (could be "group/name" or just "name")
        if "/" in key:
            group, name = key.split("/", 1)
            asset_key = AssetKey(name=name, group=group)
        else:
            asset_key = AssetKey(name=key)

        try:
            asset_def = registry.get(asset_key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Asset '{key}' not found") from None

        graph = DependencyGraph.from_registry(registry)
        check_registry = get_global_check_registry()

        # Get return type as string
        return_type = None
        if asset_def.return_type is not None:
            return_type = getattr(asset_def.return_type, "__name__", str(asset_def.return_type))

        # Get checks registered for this asset
        asset_checks = check_registry.get_checks(asset_key)
        checks = [
            CheckSchema(name=check.name, description=check.description) for check in asset_checks
        ]

        return AssetDetailSchema(
            id=str(asset_key),
            name=asset_key.name,
            group=asset_key.group,
            description=asset_def.description,
            return_type=return_type,
            dependencies=[str(dep) for dep in asset_def.dependencies],
            dependents=[str(dep) for dep in graph.reverse_adjacency.get(asset_key, ())],
            checks=checks,
        )

    @router.get("/api/plan", response_model=PlanSchema)
    async def get_plan(
        target: Annotated[str | None, Query(description="Target asset key")] = None,
    ) -> PlanSchema:
        """Get the execution plan, optionally for a specific target."""
        try:
            plan = ExecutionPlan.resolve(registry, target=target)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        steps = [
            PlanStepSchema(
                order=i + 1,
                id=str(asset_def.key),
                name=asset_def.key.name,
                group=asset_def.key.group,
            )
            for i, asset_def in enumerate(plan)
        ]

        return PlanSchema(
            target=str(plan.target) if plan.target else None,
            steps=steps,
            total_assets=len(plan),
        )

    @router.get("/health", response_model=HealthSchema)
    async def health() -> HealthSchema:
        """Health check endpoint."""
        return HealthSchema(
            status="healthy",
            version=__version__,
            asset_count=len(registry),
        )

    return router
