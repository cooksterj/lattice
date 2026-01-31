"""
Dependency graph representation and algorithms.

This module provides the DependencyGraph class for building and analyzing
asset dependency relationships. Key capabilities include topological sorting
via Kahn's algorithm, cycle detection, and upstream/downstream traversal.
"""

from collections import deque
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from lattice.exceptions import CyclicDependencyError
from lattice.models import AssetKey

if TYPE_CHECKING:
    from lattice.registry import AssetRegistry


class DependencyGraph(BaseModel):
    """
    Immutable dependency graph built from an AssetRegistry.

    The graph stores both forward edges (asset -> its dependencies) and
    reverse edges (asset -> assets that depend on it) for efficient traversal.

    Attributes
    ----------
    adjacency : dict of AssetKey to tuple of AssetKey
        Maps each asset to its dependencies (what it depends on).
    reverse_adjacency : dict of AssetKey to tuple of AssetKey
        Maps each asset to its dependents (what depends on it).
    """

    model_config = ConfigDict(frozen=True)

    adjacency: dict[AssetKey, tuple[AssetKey, ...]]
    reverse_adjacency: dict[AssetKey, tuple[AssetKey, ...]]

    @classmethod
    def from_registry(cls, registry: "AssetRegistry") -> "DependencyGraph":
        """
        Build a dependency graph from an asset registry.

        Parameters
        ----------
        registry : AssetRegistry
            The registry containing asset definitions.

        Returns
        -------
        DependencyGraph
            A new dependency graph representing the assets and their dependencies.
        """
        adjacency: dict[AssetKey, tuple[AssetKey, ...]] = {}
        reverse: dict[AssetKey, list[AssetKey]] = {}

        # Initialize all nodes
        for asset_def in registry:
            adjacency[asset_def.key] = asset_def.dependencies
            if asset_def.key not in reverse:
                reverse[asset_def.key] = []

        # Build reverse adjacency
        for asset_def in registry:
            for dep in asset_def.dependencies:
                if dep not in reverse:
                    reverse[dep] = []
                reverse[dep].append(asset_def.key)

        reverse_adjacency = {k: tuple(v) for k, v in reverse.items()}

        return cls(adjacency=adjacency, reverse_adjacency=reverse_adjacency)

    def topological_sort(self) -> list[AssetKey]:
        """
        Return assets in topological order using Kahn's algorithm.

        Assets are ordered so that dependencies come before dependents.
        Raises CyclicDependencyError if a cycle is detected.

        Returns
        -------
        list of AssetKey
            Assets in execution order (dependencies first).

        Raises
        ------
        CyclicDependencyError
            If the graph contains a cycle.
        """
        # Compute in-degrees
        in_degree: dict[AssetKey, int] = {key: 0 for key in self.adjacency}
        for key in self.adjacency:
            for dep in self.adjacency[key]:
                if dep in in_degree:
                    pass  # dep is a registered asset
                # Note: we count edges TO a node, which is reverse_adjacency

        # Actually, in_degree should count how many dependencies each node has
        # that are also in the graph
        for key in self.adjacency:
            count = 0
            for dep in self.adjacency[key]:
                if dep in self.adjacency:
                    count += 1
            in_degree[key] = count

        # Start with nodes that have no dependencies (in-degree 0)
        queue: deque[AssetKey] = deque()
        for key, degree in in_degree.items():
            if degree == 0:
                queue.append(key)

        result: list[AssetKey] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # For each node that depends on current, decrease its in-degree
            for dependent in self.reverse_adjacency.get(current, ()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # If we didn't process all nodes, there's a cycle
        if len(result) != len(self.adjacency):
            cycles = self.detect_cycles()
            if cycles:
                raise CyclicDependencyError(cycles[0])
            # Fallback error if cycle detection fails
            remaining = [k for k in self.adjacency if k not in result]
            raise CyclicDependencyError(remaining + [remaining[0]])

        return result

    def detect_cycles(self) -> list[list[AssetKey]] | None:
        """
        Detect cycles in the dependency graph using DFS.

        Returns
        -------
        list of list of AssetKey, or None
            List of cycles found (each cycle includes the repeated node),
            or None if no cycles exist.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[AssetKey, int] = {key: WHITE for key in self.adjacency}
        parent: dict[AssetKey, AssetKey | None] = {key: None for key in self.adjacency}
        cycles: list[list[AssetKey]] = []

        def dfs(node: AssetKey) -> None:
            color[node] = GRAY

            for dep in self.adjacency.get(node, ()):
                if dep not in color:
                    continue  # External dependency, not in graph

                if color[dep] == GRAY:
                    # Found a cycle - reconstruct it
                    cycle = [dep]
                    current = node
                    while current != dep:
                        cycle.append(current)
                        current = parent.get(current)  # type: ignore[assignment]
                        if current is None:
                            break
                    cycle.append(dep)
                    cycle.reverse()
                    cycles.append(cycle)
                elif color[dep] == WHITE:
                    parent[dep] = node
                    dfs(dep)

            color[node] = BLACK

        for node in self.adjacency:
            if color[node] == WHITE:
                dfs(node)

        return cycles if cycles else None

    def get_all_upstream(self, key: AssetKey) -> set[AssetKey]:
        """
        Get all transitive dependencies of an asset (ancestors).

        Upstream assets are those that must be materialized BEFORE this asset.
        For example, if C depends on B, and B depends on A, then
        get_all_upstream(C) returns {A, B}.

        Parameters
        ----------
        key : AssetKey
            The asset to get upstream dependencies for.

        Returns
        -------
        set of AssetKey
            All assets that this asset transitively depends on.
        """
        visited: set[AssetKey] = set()
        stack = list(self.adjacency.get(key, ()))

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.adjacency.get(current, ()))

        return visited

    def get_all_downstream(self, key: AssetKey) -> set[AssetKey]:
        """
        Get all transitive dependents of an asset (descendants).

        Downstream assets are those that must be re-materialized AFTER these
        asset changes. For example, if C depends on B, and B depends on A,
        then get_all_downstream(A) returns {B, C}.

        Parameters
        ----------
        key : AssetKey
            The asset to get downstream dependents for.

        Returns
        -------
        set of AssetKey
            All assets that transitively depend on this asset.
        """
        visited: set[AssetKey] = set()
        stack = list(self.reverse_adjacency.get(key, ()))

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.reverse_adjacency.get(current, ()))

        return visited

    def get_execution_levels(self, keys: list[AssetKey] | None = None) -> list[list[AssetKey]]:
        """
        Group assets into execution levels for parallel execution.

        Assets within the same level have no dependencies on each other
        and can be executed in parallel. Level 0 contains source assets
        (no dependencies), level 1 contains assets that only depend on
        level 0, and so on.

        Parameters
        ----------
        keys : list of AssetKey, optional
            Subset of keys to include. If None, includes all assets.

        Returns
        -------
        list of list of AssetKey
            Assets grouped by execution level. Each inner list can be
            executed in parallel.
        """
        if keys is None:
            keys = list(self.adjacency.keys())

        key_set = set(keys)

        # Compute the level of each node (longest path from any source)
        levels: dict[AssetKey, int] = {}

        def compute_level(key: AssetKey) -> int:
            if key in levels:
                return levels[key]

            deps_in_subset = [d for d in self.adjacency.get(key, ()) if d in key_set]
            if not deps_in_subset:
                levels[key] = 0
            else:
                levels[key] = max(compute_level(d) for d in deps_in_subset) + 1

            return levels[key]

        for key in keys:
            compute_level(key)

        # Group keys by level
        max_level = max(levels.values()) if levels else 0
        result: list[list[AssetKey]] = [[] for _ in range(max_level + 1)]

        for key in keys:
            result[levels[key]].append(key)

        return result
