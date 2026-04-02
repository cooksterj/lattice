"""Tests for DependencyGraph."""

import pytest

from lattice import (
    AssetKey,
    AssetRegistry,
    CyclicDependencyError,
    DependencyGraph,
    asset,
)


class TestDependencyGraphConstruction:
    """Tests for building DependencyGraph from registry."""

    def test_empty_registry(self, registry: AssetRegistry) -> None:
        """Empty registry produces empty graph."""
        graph = DependencyGraph.from_registry(registry)
        assert graph.adjacency == {}
        assert graph.reverse_adjacency == {}

    def test_single_asset_no_deps(self, registry: AssetRegistry) -> None:
        """Single asset with no dependencies."""

        @asset(registry=registry)
        def standalone() -> int:
            return 42

        graph = DependencyGraph.from_registry(registry)
        key = AssetKey(name="standalone")

        assert key in graph.adjacency
        assert graph.adjacency[key] == ()
        assert graph.reverse_adjacency[key] == ()

    def test_linear_chain(self, registry: AssetRegistry) -> None:
        """A -> B -> C linear dependency chain."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        graph = DependencyGraph.from_registry(registry)

        # Check adjacency (what each node depends on)
        assert graph.adjacency[AssetKey(name="a")] == ()
        assert graph.adjacency[AssetKey(name="b")] == (AssetKey(name="a"),)
        assert graph.adjacency[AssetKey(name="c")] == (AssetKey(name="b"),)

        # Check reverse adjacency (what depends on each node)
        assert graph.reverse_adjacency[AssetKey(name="a")] == (AssetKey(name="b"),)
        assert graph.reverse_adjacency[AssetKey(name="b")] == (AssetKey(name="c"),)
        assert graph.reverse_adjacency[AssetKey(name="c")] == ()

    def test_diamond_dependency(self, registry: AssetRegistry) -> None:
        """Diamond pattern: D depends on B and C, both depend on A."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a * 2

        @asset(registry=registry, deps=["a"])
        def c(a: int) -> int:
            return a * 3

        @asset(registry=registry, deps=["b", "c"])
        def d(b: int, c: int) -> int:
            return b + c

        graph = DependencyGraph.from_registry(registry)

        # D depends on both B and C
        assert set(graph.adjacency[AssetKey(name="d")]) == {
            AssetKey(name="b"),
            AssetKey(name="c"),
        }

        # A has two dependents
        assert set(graph.reverse_adjacency[AssetKey(name="a")]) == {
            AssetKey(name="b"),
            AssetKey(name="c"),
        }


class TestTopologicalSort:
    """Tests for topological sorting."""

    def test_empty_graph(self, registry: AssetRegistry) -> None:
        """Empty graph returns empty list."""
        graph = DependencyGraph.from_registry(registry)
        assert graph.topological_sort() == []

    def test_single_asset(self, registry: AssetRegistry) -> None:
        """Single asset returns that asset."""

        @asset(registry=registry)
        def only() -> int:
            return 1

        graph = DependencyGraph.from_registry(registry)
        result = graph.topological_sort()

        assert result == [AssetKey(name="only")]

    def test_linear_chain_order(self, registry: AssetRegistry) -> None:
        """Linear chain is sorted correctly."""

        @asset(registry=registry)
        def first() -> int:
            return 1

        @asset(registry=registry, deps=["first"])
        def second(first: int) -> int:
            return first + 1

        @asset(registry=registry, deps=["second"])
        def third(second: int) -> int:
            return second + 1

        graph = DependencyGraph.from_registry(registry)
        result = graph.topological_sort()

        # Dependencies must come before dependents
        assert result.index(AssetKey(name="first")) < result.index(AssetKey(name="second"))
        assert result.index(AssetKey(name="second")) < result.index(AssetKey(name="third"))

    def test_diamond_order(self, registry: AssetRegistry) -> None:
        """Diamond pattern sorts correctly."""

        @asset(registry=registry)
        def root() -> int:
            return 1

        @asset(registry=registry, deps=["root"])
        def left(root: int) -> int:
            return root * 2

        @asset(registry=registry, deps=["root"])
        def right(root: int) -> int:
            return root * 3

        @asset(registry=registry, deps=["left", "right"])
        def leaf(left: int, right: int) -> int:
            return left + right

        graph = DependencyGraph.from_registry(registry)
        result = graph.topological_sort()

        # Root must be first
        assert result[0] == AssetKey(name="root")
        # Leaf must be last
        assert result[-1] == AssetKey(name="leaf")
        # Left and right must be in the middle
        assert AssetKey(name="left") in result[1:3]
        assert AssetKey(name="right") in result[1:3]

    def test_independent_assets(self, registry: AssetRegistry) -> None:
        """Independent assets can be in any order."""

        @asset(registry=registry)
        def alpha() -> int:
            return 1

        @asset(registry=registry)
        def beta() -> int:
            return 2

        @asset(registry=registry)
        def gamma() -> int:
            return 3

        graph = DependencyGraph.from_registry(registry)
        result = graph.topological_sort()

        # All three should be present
        assert len(result) == 3
        assert set(result) == {
            AssetKey(name="alpha"),
            AssetKey(name="beta"),
            AssetKey(name="gamma"),
        }


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_no_cycles_returns_none(self, registry: AssetRegistry) -> None:
        """Graph without cycles returns None."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        graph = DependencyGraph.from_registry(registry)
        assert graph.detect_cycles() is None

    def test_topological_sort_raises_on_cycle(self) -> None:
        """Topological sort raises CyclicDependencyError on cycle."""
        # Manually create a cyclic graph (can't do this with @asset decorator)
        key_a = AssetKey(name="a")
        key_b = AssetKey(name="b")

        graph = DependencyGraph(
            adjacency={
                key_a: (key_b,),  # a depends on b
                key_b: (key_a,),  # b depends on a (cycle!)
            },
            reverse_adjacency={
                key_a: (key_b,),
                key_b: (key_a,),
            },
        )

        with pytest.raises(CyclicDependencyError) as exc_info:
            graph.topological_sort()

        # Cycle should be reported
        assert len(exc_info.value.cycle) >= 2


class TestUpstreamDownstream:
    """Tests for upstream/downstream traversal."""

    def test_get_all_upstream_leaf(self, registry: AssetRegistry) -> None:
        """Leaf node has all ancestors as upstream."""

        @asset(registry=registry)
        def source() -> int:
            return 1

        @asset(registry=registry, deps=["source"])
        def middle(source: int) -> int:
            return source + 1

        @asset(registry=registry, deps=["middle"])
        def sink(middle: int) -> int:
            return middle + 1

        graph = DependencyGraph.from_registry(registry)

        upstream = graph.get_all_upstream(AssetKey(name="sink"))
        assert upstream == {AssetKey(name="source"), AssetKey(name="middle")}

    def test_get_all_upstream_root(self, registry: AssetRegistry) -> None:
        """Root node has no upstream."""

        @asset(registry=registry)
        def root() -> int:
            return 1

        @asset(registry=registry, deps=["root"])
        def child(root: int) -> int:
            return root + 1

        graph = DependencyGraph.from_registry(registry)

        upstream = graph.get_all_upstream(AssetKey(name="root"))
        assert upstream == set()

    def test_get_all_downstream_root(self, registry: AssetRegistry) -> None:
        """Root node has all descendants as downstream."""

        @asset(registry=registry)
        def root() -> int:
            return 1

        @asset(registry=registry, deps=["root"])
        def mid(root: int) -> int:
            return root + 1

        @asset(registry=registry, deps=["mid"])
        def leaf(mid: int) -> int:
            return mid + 1

        graph = DependencyGraph.from_registry(registry)

        downstream = graph.get_all_downstream(AssetKey(name="root"))
        assert downstream == {AssetKey(name="mid"), AssetKey(name="leaf")}

    def test_get_all_downstream_leaf(self, registry: AssetRegistry) -> None:
        """Leaf node has no downstream."""

        @asset(registry=registry)
        def parent() -> int:
            return 1

        @asset(registry=registry, deps=["parent"])
        def leaf(parent: int) -> int:
            return parent + 1

        graph = DependencyGraph.from_registry(registry)

        downstream = graph.get_all_downstream(AssetKey(name="leaf"))
        assert downstream == set()

    def test_diamond_upstream(self, registry: AssetRegistry) -> None:
        """Diamond pattern upstream traversal."""

        @asset(registry=registry)
        def top() -> int:
            return 1

        @asset(registry=registry, deps=["top"])
        def left(top: int) -> int:
            return top * 2

        @asset(registry=registry, deps=["top"])
        def right(top: int) -> int:
            return top * 3

        @asset(registry=registry, deps=["left", "right"])
        def bottom(left: int, right: int) -> int:
            return left + right

        graph = DependencyGraph.from_registry(registry)

        upstream = graph.get_all_upstream(AssetKey(name="bottom"))
        assert upstream == {
            AssetKey(name="top"),
            AssetKey(name="left"),
            AssetKey(name="right"),
        }


class TestExecutionLevels:
    """Tests for DependencyGraph.get_execution_levels()."""

    def test_single_asset_no_deps(self, registry: AssetRegistry) -> None:
        """Single asset with no deps returns one level."""

        @asset(registry=registry)
        def single() -> int:
            return 1

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels()

        assert levels == [[AssetKey(name="single")]]

    def test_linear_chain(self, registry: AssetRegistry) -> None:
        """Linear chain a -> b -> c produces three levels."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels()

        assert len(levels) == 3
        assert levels[0] == [AssetKey(name="a")]
        assert levels[1] == [AssetKey(name="b")]
        assert levels[2] == [AssetKey(name="c")]

    def test_diamond_pattern(self, registry: AssetRegistry) -> None:
        """Diamond: a -> b,c -> d. b and c should be at the same level."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a * 2

        @asset(registry=registry, deps=["a"])
        def c(a: int) -> int:
            return a * 3

        @asset(registry=registry, deps=["b", "c"])
        def d(b: int, c: int) -> int:
            return b + c

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels()

        assert len(levels) == 3
        assert levels[0] == [AssetKey(name="a")]
        assert set(levels[1]) == {AssetKey(name="b"), AssetKey(name="c")}
        assert levels[2] == [AssetKey(name="d")]

    def test_independent_assets_all_level_zero(self, registry: AssetRegistry) -> None:
        """Independent assets with no deps are all at level 0."""

        @asset(registry=registry)
        def alpha() -> int:
            return 1

        @asset(registry=registry)
        def beta() -> int:
            return 2

        @asset(registry=registry)
        def gamma() -> int:
            return 3

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels()

        assert len(levels) == 1
        assert set(levels[0]) == {
            AssetKey(name="alpha"),
            AssetKey(name="beta"),
            AssetKey(name="gamma"),
        }

    def test_subset_key_filtering(self, registry: AssetRegistry) -> None:
        """Passing a subset of keys includes only those keys."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        graph = DependencyGraph.from_registry(registry)

        # Only include a and b, not c
        levels = graph.get_execution_levels(keys=[AssetKey(name="a"), AssetKey(name="b")])

        all_keys = [k for level in levels for k in level]
        assert AssetKey(name="a") in all_keys
        assert AssetKey(name="b") in all_keys
        assert AssetKey(name="c") not in all_keys

    def test_empty_keys_list(self, registry: AssetRegistry) -> None:
        """Empty keys list returns a single empty level."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels(keys=[])

        assert levels == [[]]

    def test_none_keys_includes_all(self, registry: AssetRegistry) -> None:
        """Passing keys=None includes all assets in the graph."""

        @asset(registry=registry)
        def x() -> int:
            return 1

        @asset(registry=registry, deps=["x"])
        def y(x: int) -> int:
            return x + 1

        graph = DependencyGraph.from_registry(registry)
        levels = graph.get_execution_levels(keys=None)

        all_keys = {k for level in levels for k in level}
        assert all_keys == {AssetKey(name="x"), AssetKey(name="y")}


class TestDfsCycleDetect:
    """Tests for the _dfs_cycle_detect helper function."""

    def test_simple_two_node_cycle(self) -> None:
        """Two nodes forming a cycle are detected."""
        from lattice.graph.algorithms import _dfs_cycle_detect

        key_a = AssetKey(name="a")
        key_b = AssetKey(name="b")

        adjacency = {key_a: (key_b,), key_b: (key_a,)}
        WHITE = 0
        color: dict[AssetKey, int] = {key_a: WHITE, key_b: WHITE}
        parent: dict[AssetKey, AssetKey | None] = {key_a: None, key_b: None}
        cycles: list[list[AssetKey]] = []

        _dfs_cycle_detect(key_a, adjacency, color, parent, cycles)

        assert len(cycles) >= 1

    def test_no_cycle(self) -> None:
        """Acyclic graph produces no cycles."""
        from lattice.graph.algorithms import _dfs_cycle_detect

        key_a = AssetKey(name="a")
        key_b = AssetKey(name="b")

        adjacency = {key_a: (key_b,), key_b: ()}
        WHITE = 0
        color: dict[AssetKey, int] = {key_a: WHITE, key_b: WHITE}
        parent: dict[AssetKey, AssetKey | None] = {key_a: None, key_b: None}
        cycles: list[list[AssetKey]] = []

        _dfs_cycle_detect(key_a, adjacency, color, parent, cycles)

        assert cycles == []

    def test_external_dep_skipped(self) -> None:
        """Dependency not in color dict is gracefully skipped."""
        from lattice.graph.algorithms import _dfs_cycle_detect

        key_a = AssetKey(name="a")
        key_external = AssetKey(name="external")

        # a depends on external, but external is NOT in color dict
        adjacency: dict[AssetKey, tuple[AssetKey, ...]] = {key_a: (key_external,)}
        WHITE = 0
        color: dict[AssetKey, int] = {key_a: WHITE}
        parent: dict[AssetKey, AssetKey | None] = {key_a: None}
        cycles: list[list[AssetKey]] = []

        _dfs_cycle_detect(key_a, adjacency, color, parent, cycles)

        assert cycles == []


class TestComputeLevel:
    """Tests for the _compute_level helper function."""

    def test_root_node_returns_zero(self) -> None:
        """Node with no dependencies returns level 0."""
        from lattice.graph.algorithms import _compute_level

        key_a = AssetKey(name="a")
        adjacency: dict[AssetKey, tuple[AssetKey, ...]] = {key_a: ()}
        levels: dict[AssetKey, int] = {}
        key_set = {key_a}

        result = _compute_level(key_a, adjacency, levels, key_set)

        assert result == 0
        assert levels[key_a] == 0

    def test_linear_chain_depth(self) -> None:
        """Node at end of a -> b -> c chain returns level 2."""
        from lattice.graph.algorithms import _compute_level

        key_a = AssetKey(name="a")
        key_b = AssetKey(name="b")
        key_c = AssetKey(name="c")

        adjacency: dict[AssetKey, tuple[AssetKey, ...]] = {
            key_a: (),
            key_b: (key_a,),
            key_c: (key_b,),
        }
        levels: dict[AssetKey, int] = {}
        key_set = {key_a, key_b, key_c}

        result = _compute_level(key_c, adjacency, levels, key_set)

        assert result == 2
        assert levels[key_a] == 0
        assert levels[key_b] == 1
        assert levels[key_c] == 2

    def test_memoization(self) -> None:
        """Second call for same key reuses cached value from levels dict."""
        from lattice.graph.algorithms import _compute_level

        key_a = AssetKey(name="a")
        adjacency: dict[AssetKey, tuple[AssetKey, ...]] = {key_a: ()}
        levels: dict[AssetKey, int] = {}
        key_set = {key_a}

        result1 = _compute_level(key_a, adjacency, levels, key_set)
        assert key_a in levels

        # Calling again should return the same value from the dict
        result2 = _compute_level(key_a, adjacency, levels, key_set)
        assert result1 == result2 == 0
