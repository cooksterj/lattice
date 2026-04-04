"""Pydantic schemas for graph and asset API responses."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class CheckSchema(BaseModel):
    """Schema for a registered check."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None


class NodeSchema(BaseModel):
    """Graph node representing an asset."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    group: str
    description: str | None = None
    return_type: str | None = None
    dependency_count: int = 0
    dependent_count: int = 0
    checks: list[CheckSchema] = []
    metadata: dict[str, Any] | None = None
    execution_type: str = "python"


class AssetCatalogItemSchema(BaseModel):
    """Summary schema for asset catalog listing."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    group: str
    description: str | None = None
    dependency_count: int = 0
    dependent_count: int = 0
    check_count: int = 0
    metadata: dict[str, Any] | None = None
    execution_type: str = "python"


class EdgeSchema(BaseModel):
    """Graph edge representing a dependency relationship."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str


class ExternalEdgeSchema(BaseModel):
    """Edge crossing a group boundary to or from an external asset."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    external_asset: str
    direction: str


class GraphSchema(BaseModel):
    """Complete graph data for visualization."""

    model_config = ConfigDict(frozen=True)

    nodes: list[NodeSchema]
    edges: list[EdgeSchema]


class AssetGroupSchema(BaseModel):
    """Named group of assets with summary metadata."""

    model_config = ConfigDict(frozen=True)

    name: str
    asset_count: int
    assets: list[AssetCatalogItemSchema]


class GroupedAssetsSchema(BaseModel):
    """Assets partitioned into named groups and ungrouped standalone assets."""

    model_config = ConfigDict(frozen=True)

    groups: list[AssetGroupSchema]
    ungrouped_assets: list[AssetCatalogItemSchema]


class GroupGraphSchema(BaseModel):
    """Dependency subgraph scoped to a single asset group."""

    model_config = ConfigDict(frozen=True)

    group_name: str
    nodes: list[NodeSchema]
    edges: list[EdgeSchema]
    external_edges: list[ExternalEdgeSchema]


class OverviewNodeSchema(BaseModel):
    """Node in the overview meta-graph (group super-node or standalone asset)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    node_type: str
    asset_count: int
    group: str
    execution_type: str | None = None
    check_count: int = 0


class OverviewEdgeSchema(BaseModel):
    """Edge in the overview meta-graph."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str


class OverviewGraphSchema(BaseModel):
    """Meta-graph showing groups and standalone assets with connections."""

    model_config = ConfigDict(frozen=True)

    nodes: list[OverviewNodeSchema]
    edges: list[OverviewEdgeSchema]


class AssetDetailSchema(BaseModel):
    """Detailed asset information."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    group: str
    description: str | None = None
    return_type: str | None = None
    dependencies: list[str]
    dependents: list[str]
    checks: list[CheckSchema] = []
    metadata: dict[str, Any] | None = None
    execution_type: str = "python"


class PlanStepSchema(BaseModel):
    """A step in the execution plan."""

    model_config = ConfigDict(frozen=True)

    order: int
    id: str
    name: str
    group: str


class PlanSchema(BaseModel):
    """Execution plan response."""

    model_config = ConfigDict(frozen=True)

    target: str | None = None
    steps: list[PlanStepSchema]
    total_assets: int


class HealthSchema(BaseModel):
    """Health check response."""

    model_config = ConfigDict(frozen=True)

    status: str
    version: str
    asset_count: int
