"""Core data models for Lattice."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssetKey(BaseModel):
    """Unique identifier for an asset.

    Assets can be organized into groups for namespacing.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1)
    group: str = Field(default="default", min_length=1)

    def __str__(self) -> str:
        return f"{self.group}/{self.name}" if self.group != "default" else self.name

    def __hash__(self) -> int:
        return hash((self.group, self.name))


class AssetDefinition(BaseModel):
    """Metadata wrapper for an asset function."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: AssetKey
    fn: Callable[..., Any]
    dependencies: tuple[AssetKey, ...] = Field(default_factory=tuple)
    return_type: Any = None  # Can be type, GenericAlias, or None
    description: str | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the underlying asset function."""
        return self.fn(*args, **kwargs)

    def __hash__(self) -> int:
        return hash(self.key)
