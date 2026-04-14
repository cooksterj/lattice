"""API routes for graph and asset visualization."""

from __future__ import annotations

from typing import Annotated, Any

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
    AssetCatalogItemSchema,
    AssetDetailSchema,
    AssetGroupSchema,
    CheckSchema,
    EdgeSchema,
    ExternalEdgeSchema,
    GraphSchema,
    GroupedAssetsSchema,
    GroupGraphSchema,
    HealthSchema,
    NodeSchema,
    OverviewEdgeSchema,
    OverviewGraphSchema,
    OverviewNodeSchema,
    PlanSchema,
    PlanStepSchema,
)


def _resolve_execution_type(metadata: dict[str, Any] | None) -> str:
    """Derive execution type from asset metadata."""
    if metadata is not None:
        source = metadata.get("source")
        if source in {"dbt", "shell"}:
            return str(source)
    return "python"


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
    async def groups_page(request: Request) -> HTMLResponse:
        """Serve the groups landing page."""
        return templates.TemplateResponse(request, "groups.html", {"current_page": "groups"})

    @router.get("/pipeline", response_class=HTMLResponse)
    async def pipeline_page(request: Request) -> HTMLResponse:
        """Serve the full pipeline visualization page."""
        return templates.TemplateResponse(request, "index.html", {"current_page": "pipeline"})

    @router.get("/group/{name}", response_class=HTMLResponse)
    async def group_detail_page(request: Request, name: str) -> HTMLResponse:
        """Serve the group detail page with dependency graph."""
        return templates.TemplateResponse(
            request, "group_detail.html", {"group_name": name, "current_page": "groups"}
        )

    @router.get("/runs", response_class=HTMLResponse)
    async def runs_page(request: Request) -> HTMLResponse:
        """Serve the active runs monitoring page."""
        return templates.TemplateResponse(request, "runs.html", {"current_page": "runs"})

    @router.get("/assets", response_class=HTMLResponse)
    async def assets_page(request: Request) -> HTMLResponse:
        """Serve the asset catalog page."""
        return templates.TemplateResponse(request, "assets.html", {"current_page": "assets"})

    @router.get("/asset/{key:path}/live", response_class=HTMLResponse)
    async def asset_live(request: Request, key: str) -> HTMLResponse:
        """Serve the asset live monitoring page."""
        return templates.TemplateResponse(
            request, "asset_live.html", {"asset_key": key, "current_page": "pipeline"}
        )

    @router.get("/asset/{key:path}", response_class=HTMLResponse)
    async def asset_detail(request: Request, key: str) -> HTMLResponse:
        """Serve the asset detail page with run history."""
        return templates.TemplateResponse(
            request, "asset_detail.html", {"asset_key": key, "current_page": "history"}
        )

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
                    metadata=asset_def.metadata,
                    execution_type=_resolve_execution_type(asset_def.metadata),
                )
            )

            # Add edges for dependencies
            for dep in asset_def.dependencies:
                if dep in registry:
                    edges.append(EdgeSchema(source=str(dep), target=node_id))

        return GraphSchema(nodes=nodes, edges=edges)

    @router.get("/api/assets", response_model=list[AssetCatalogItemSchema])
    async def list_assets() -> list[AssetCatalogItemSchema]:
        """List all registered assets for the catalog."""
        graph = DependencyGraph.from_registry(registry)
        check_registry = get_global_check_registry()

        items: list[AssetCatalogItemSchema] = []
        for asset_def in registry:
            key = asset_def.key
            asset_checks = check_registry.get_checks(key)

            items.append(
                AssetCatalogItemSchema(
                    id=str(key),
                    name=key.name,
                    group=key.group,
                    description=asset_def.description,
                    dependency_count=len(asset_def.dependencies),
                    dependent_count=len(graph.reverse_adjacency.get(key, ())),
                    check_count=len(asset_checks),
                    metadata=asset_def.metadata,
                    execution_type=_resolve_execution_type(asset_def.metadata),
                )
            )

        return items

    @router.get("/api/assets/overview", response_model=OverviewGraphSchema)
    async def get_overview_graph() -> OverviewGraphSchema:
        """Get a meta-graph showing groups and standalone assets with connections."""
        check_registry = get_global_check_registry()

        # Partition assets by group
        groups_map: dict[str, set[AssetKey]] = {}
        standalone: set[AssetKey] = set()

        for asset_def in registry:
            key = asset_def.key
            if key.group == "default":
                standalone.add(key)
            else:
                groups_map.setdefault(key.group, set()).add(key)

        # Build nodes
        nodes: list[OverviewNodeSchema] = []
        for group_name, keys in sorted(groups_map.items()):
            group_check_count = sum(len(check_registry.get_checks(k)) for k in keys)
            nodes.append(
                OverviewNodeSchema(
                    id=f"group:{group_name}",
                    name=group_name,
                    node_type="group",
                    asset_count=len(keys),
                    group=group_name,
                    check_count=group_check_count,
                )
            )

        for key in sorted(standalone, key=str):
            asset_def = registry.get(key)
            nodes.append(
                OverviewNodeSchema(
                    id=str(key),
                    name=key.name,
                    node_type="asset",
                    asset_count=1,
                    group="default",
                    execution_type=_resolve_execution_type(asset_def.metadata),
                    check_count=len(check_registry.get_checks(key)),
                )
            )

        # Build deduplicated edges
        edge_set: set[tuple[str, str]] = set()

        for asset_def in registry:
            key = asset_def.key
            target_node = f"group:{key.group}" if key.group != "default" else str(key)

            for dep in asset_def.dependencies:
                if dep not in registry:
                    continue
                source_node = f"group:{dep.group}" if dep.group != "default" else str(dep)

                # Skip self-loops (intra-group edges collapse)
                if source_node == target_node:
                    continue

                edge_set.add((source_node, target_node))

        edges = [OverviewEdgeSchema(source=src, target=tgt) for src, tgt in sorted(edge_set)]

        return OverviewGraphSchema(nodes=nodes, edges=edges)

    @router.get("/api/assets/grouped", response_model=GroupedAssetsSchema)
    async def get_grouped_assets() -> GroupedAssetsSchema:
        """Get assets organized into named groups and ungrouped standalone assets."""
        graph = DependencyGraph.from_registry(registry)
        check_registry = get_global_check_registry()

        groups_map: dict[str, list[AssetCatalogItemSchema]] = {}
        ungrouped: list[AssetCatalogItemSchema] = []

        for asset_def in registry:
            key = asset_def.key
            asset_checks = check_registry.get_checks(key)

            item = AssetCatalogItemSchema(
                id=str(key),
                name=key.name,
                group=key.group,
                description=asset_def.description,
                dependency_count=len(asset_def.dependencies),
                dependent_count=len(graph.reverse_adjacency.get(key, ())),
                check_count=len(asset_checks),
                metadata=asset_def.metadata,
                execution_type=_resolve_execution_type(asset_def.metadata),
            )

            if key.group == "default":
                ungrouped.append(item)
            else:
                groups_map.setdefault(key.group, []).append(item)

        groups = [
            AssetGroupSchema(name=name, asset_count=len(assets), assets=assets)
            for name, assets in sorted(groups_map.items())
        ]

        return GroupedAssetsSchema(groups=groups, ungrouped_assets=ungrouped)

    @router.get("/api/groups/{name}/graph", response_model=GroupGraphSchema)
    async def get_group_graph(name: str) -> GroupGraphSchema:
        """Get dependency subgraph scoped to a single asset group."""
        graph = DependencyGraph.from_registry(registry)
        check_registry = get_global_check_registry()

        # Collect assets in this group
        group_keys: set[AssetKey] = set()
        for asset_def in registry:
            if asset_def.key.group == name:
                group_keys.add(asset_def.key)

        if not group_keys:
            raise HTTPException(status_code=404, detail=f"Group '{name}' not found") from None

        nodes: list[NodeSchema] = []
        edges: list[EdgeSchema] = []
        external_edges: list[ExternalEdgeSchema] = []

        for asset_def in registry:
            key = asset_def.key
            if key not in group_keys:
                continue

            node_id = str(key)
            return_type = None
            if asset_def.return_type is not None:
                return_type = getattr(asset_def.return_type, "__name__", str(asset_def.return_type))

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
                    metadata=asset_def.metadata,
                    execution_type=_resolve_execution_type(asset_def.metadata),
                )
            )

            # Intra-group edges and external inbound edges
            for dep in asset_def.dependencies:
                if dep in group_keys:
                    edges.append(EdgeSchema(source=str(dep), target=node_id))
                elif dep in registry:
                    external_edges.append(
                        ExternalEdgeSchema(
                            source=str(dep),
                            target=node_id,
                            external_asset=str(dep),
                            direction="inbound",
                        )
                    )

        # External outbound edges (assets outside group that depend on group assets)
        for asset_def in registry:
            if asset_def.key in group_keys:
                continue
            for dep in asset_def.dependencies:
                if dep in group_keys:
                    external_edges.append(
                        ExternalEdgeSchema(
                            source=str(dep),
                            target=str(asset_def.key),
                            external_asset=str(asset_def.key),
                            direction="outbound",
                        )
                    )

        return GroupGraphSchema(
            group_name=name,
            nodes=nodes,
            edges=edges,
            external_edges=external_edges,
        )

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
            metadata=asset_def.metadata,
            execution_type=_resolve_execution_type(asset_def.metadata),
        )

    @router.get("/api/plan", response_model=PlanSchema)
    async def get_plan(
        target: Annotated[str | None, Query(description="Target asset key")] = None,
        include_downstream: Annotated[
            bool,
            Query(
                description=(
                    "When `target` is set, also include assets downstream of the "
                    "target. Has no effect when `target` is omitted — the full "
                    "plan is already returned in that case."
                )
            ),
        ] = False,
    ) -> PlanSchema:
        """Get the execution plan, optionally scoped to a target and its downstream."""
        try:
            plan = ExecutionPlan.resolve(
                registry, target=target, include_downstream=include_downstream
            )
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
