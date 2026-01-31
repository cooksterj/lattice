"""
Execution plan for asset materialization.

This module provides the ExecutionPlan class which resolves the order in
which assets must be materialized based on their dependencies. Plans can
target a specific asset (including only required upstream assets) or
include all registered assets.
"""

import logging
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from lattice.graph import DependencyGraph
from lattice.models import AssetDefinition, AssetKey
from lattice.registry import AssetRegistry

logger = logging.getLogger(__name__)


class ExecutionPlan(BaseModel):
    """
    An ordered plan for materializing assets.

    The plan contains assets in topological order, ensuring dependencies
    are materialized before the assets that depend on them.

    Attributes
    ----------
    assets : tuple of AssetDefinition
        Assets in execution order (dependencies first).
    target : AssetKey or None
        The target asset if a subset was resolved, None for full graph.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    assets: tuple[AssetDefinition, ...]
    target: AssetKey | None = None

    @classmethod
    def resolve(
        cls,
        registry: AssetRegistry,
        target: AssetKey | str | None = None,
        include_downstream: bool = False,
    ) -> "ExecutionPlan":
        """
        Resolve an execution plan from a registry.

        If a target is specified, only include assets required to materialize
        that target (upstream dependencies). If include_downstream is True,
        include the target and all assets that depend on it instead.

        Parameters
        ----------
        registry : AssetRegistry
            The registry containing asset definitions.
        target : AssetKey, str, or None
            Optional target asset to resolve. If string, converted to AssetKey.
        include_downstream : bool
            If True and target is specified, include the target and all
            downstream dependents instead of upstream dependencies.

        Returns
        -------
        ExecutionPlan
            An execution plan with assets in topological order.

        Raises
        ------
        KeyError
            If the target asset is not found in the registry.
        CyclicDependencyError
            If a cycle is detected in the dependency graph.
        """
        # Normalize target to AssetKey
        target_key: AssetKey | None = None
        if target is not None:
            if isinstance(target, str):
                # Parse "group/name" format or just "name"
                if "/" in target:
                    group, name = target.split("/", 1)
                    target_key = AssetKey(name=name, group=group)
                else:
                    target_key = AssetKey(name=target)
            else:
                target_key = target

        # Build dependency graph
        graph = DependencyGraph.from_registry(registry)

        # Get topological order
        sorted_keys = graph.topological_sort()

        # If target specified, filter to only required assets
        if target_key is not None:
            if target_key not in registry:
                raise KeyError(f"Target asset {target_key} not found in registry")

            if include_downstream:
                # Include target, its upstream dependencies, AND all downstream dependents
                # Use case: "execute from this asset and refresh everything downstream"
                required = graph.get_all_upstream(target_key)  # Upstream needed to run target
                required.add(target_key)
                required.update(graph.get_all_downstream(target_key))  # Plus downstream
            else:
                # Include target and all upstream dependencies
                required = graph.get_all_upstream(target_key)
                required.add(target_key)
            sorted_keys = [k for k in sorted_keys if k in required]

        # Convert keys to asset definitions
        assets = tuple(registry.get(key) for key in sorted_keys)

        logger.debug(
            "Resolved execution plan: target=%s, assets=%d",
            target_key or "all",
            len(assets),
        )

        return cls(assets=assets, target=target_key)

    def __iter__(self) -> Iterator[AssetDefinition]:  # type: ignore[override]
        """
        Iterate over assets in execution order.

        Yields
        ------
        AssetDefinition
            Each asset definition in the plan.
        """
        return iter(self.assets)

    def __len__(self) -> int:
        """
        Return the number of assets in the plan.

        Returns
        -------
        int
            The count of assets.
        """
        return len(self.assets)

    def __contains__(self, key: AssetKey | str) -> bool:
        """
        Check if an asset is in the plan.

        Parameters
        ----------
        key : AssetKey or str
            The asset key to check. String format: "name" or "group/name".

        Returns
        -------
        bool
            True if the asset is in the plan.
        """
        if isinstance(key, str):
            if "/" in key:
                group, name = key.split("/", 1)
                key = AssetKey(name=name, group=group)
            else:
                key = AssetKey(name=key)
        return any(asset.key == key for asset in self.assets)
