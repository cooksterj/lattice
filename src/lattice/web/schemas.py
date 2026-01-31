"""Pydantic schemas for graph and asset API responses."""

from pydantic import BaseModel, ConfigDict


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


class EdgeSchema(BaseModel):
    """Graph edge representing a dependency relationship."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str


class GraphSchema(BaseModel):
    """Complete graph data for visualization."""

    model_config = ConfigDict(frozen=True)

    nodes: list[NodeSchema]
    edges: list[EdgeSchema]


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
