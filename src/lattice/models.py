"""
Core data models for Lattice.

This module defines the foundational Pydantic models used throughout the
framework: AssetKey for unique asset identification with optional group
namespacing, and AssetDefinition for wrapping asset functions with their
metadata (dependencies, return type, description).
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssetKey(BaseModel):
    """
    Unique identifier for an asset.

    Assets can be organized into groups for namespacing.

    Attributes
    ----------
    name : str
        The asset name. Must be at least 1 character.
    group : str
        The namespace group. Defaults to "default".
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1)
    group: str = Field(default="default", min_length=1)

    def __str__(self) -> str:
        """
        Return string representation of the asset key.

        Returns
        -------
        str
            Format "group/name" if the group is not default, otherwise just "name".
        """
        return f"{self.group}/{self.name}" if self.group != "default" else self.name

    def __hash__(self) -> int:
        """
        Return hash based on group and name.

        Returns
        -------
        int
            Hash value for use in sets and dict keys.
        """
        return hash((self.group, self.name))


class AssetDefinition(BaseModel):
    """
    Metadata wrapper for an asset function.

    Attributes
    ----------
    key : AssetKey
        Unique identifier for this asset.
    fn : Callable[..., Any]
        The underlying asset function.
    dependencies : tuple of AssetKey
        Other assets this asset depends on.
    dependency_params : tuple of str
        Parameter names corresponding to each dependency (same order).
    return_type : Any
        The return type annotation. Can be type, GenericAlias, or None.
    description : str or None
        Optional human-readable description.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: AssetKey
    fn: Callable[..., Any]
    dependencies: tuple[AssetKey, ...] = Field(default_factory=tuple)
    dependency_params: tuple[str, ...] = Field(default_factory=tuple)
    return_type: Any = None  # Can be type, GenericAlias, or None
    description: str | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute the underlying asset function.

        Parameters
        ----------
        *args : Any
            Positional arguments passed to the asset function.
        **kwargs : Any
            Keyword arguments passed to the asset function.

        Returns
        -------
        Any
            The result of the asset function.
        """
        return self.fn(*args, **kwargs)

    def __hash__(self) -> int:
        """
        Return hash based on the asset key.

        Returns
        -------
        int
            Hash value for use in sets and dict keys.
        """
        return hash(self.key)
