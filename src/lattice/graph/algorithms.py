"""Graph algorithms for dependency analysis.

This module provides the core graph algorithms used by DependencyGraph:
DFS-based cycle detection and execution level computation.
"""

from lattice.models import AssetKey


def _dfs_cycle_detect(
    node: AssetKey,
    adjacency: dict[AssetKey, tuple[AssetKey, ...]],
    color: dict[AssetKey, int],
    parent: dict[AssetKey, AssetKey | None],
    cycles: list[list[AssetKey]],
) -> None:
    """Traverse a node via depth-first search (DFS) and record any back-edge cycles.

    DFS is a graph traversal strategy that explores as far as possible
    along each branch before backtracking. This makes it well-suited for
    cycle detection: by tracking which nodes are on the current recursion
    stack we can identify back-edges — edges that point back to an
    ancestor — which are the definitive indicator of a cycle in a
    directed graph.

    This implementation uses the three-color algorithm to classify each
    node's visitation state:

    - **WHITE (0)** — not yet visited.
    - **GRAY (1)** — currently on the recursion stack (being explored).
    - **BLACK (2)** — fully explored, all descendants processed.

    When a GRAY node is encountered from another GRAY node, a cycle
    exists. The cycle path is reconstructed by walking the ``parent``
    chain back to the repeated node and appended to ``cycles``.

    Parameters
    ----------
    node : AssetKey
        The node to visit.
    adjacency : dict[AssetKey, tuple[AssetKey, ...]]
        Forward-edge adjacency map for the graph.
    color : dict[AssetKey, int]
        Mutable mapping of node visitation state (0=WHITE, 1=GRAY, 2=BLACK).
    parent : dict[AssetKey, AssetKey | None]
        Mutable mapping tracking the DFS parent of each visited node.
    cycles : list[list[AssetKey]]
        Mutable accumulator for detected cycles.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color[node] = GRAY

    for dep in adjacency.get(node, ()):
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
            _dfs_cycle_detect(dep, adjacency, color, parent, cycles)

    color[node] = BLACK


def _compute_level(
    key: AssetKey,
    adjacency: dict[AssetKey, tuple[AssetKey, ...]],
    levels: dict[AssetKey, int],
    key_set: set[AssetKey],
) -> int:
    """Compute the execution level for an asset with memoization.

    Level 0 is assigned to assets with no in-subset dependencies.
    All other assets receive ``max(dependency levels) + 1``. Results
    are cached in ``levels`` to avoid redundant recursion.

    Parameters
    ----------
    key : AssetKey
        The asset whose level to compute.
    adjacency : dict[AssetKey, tuple[AssetKey, ...]]
        Forward-edge adjacency map for the graph.
    levels : dict[AssetKey, int]
        Mutable memoization cache of previously computed levels.
    key_set : set[AssetKey]
        Subset of keys to consider when resolving dependencies.

    Returns
    -------
    int
        The execution level (0-based).
    """
    if key in levels:
        return levels[key]

    deps_in_subset = [d for d in adjacency.get(key, ()) if d in key_set]
    if not deps_in_subset:
        levels[key] = 0
    else:
        levels[key] = max(_compute_level(d, adjacency, levels, key_set) for d in deps_in_subset) + 1

    return levels[key]
