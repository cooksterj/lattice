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

        @asset(registry=registry)
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry)
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

        @asset(registry=registry)
        def b(a: int) -> int:
            return a * 2

        @asset(registry=registry)
        def c(a: int) -> int:
            return a * 3

        @asset(registry=registry)
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

        @asset(registry=registry)
        def second(first: int) -> int:
            return first + 1

        @asset(registry=registry)
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

        @asset(registry=registry)
        def left(root: int) -> int:
            return root * 2

        @asset(registry=registry)
        def right(root: int) -> int:
            return root * 3

        @asset(registry=registry)
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

        @asset(registry=registry)
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

        @asset(registry=registry)
        def middle(source: int) -> int:
            return source + 1

        @asset(registry=registry)
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

        @asset(registry=registry)
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

        @asset(registry=registry)
        def mid(root: int) -> int:
            return root + 1

        @asset(registry=registry)
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

        @asset(registry=registry)
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

        @asset(registry=registry)
        def left(top: int) -> int:
            return top * 2

        @asset(registry=registry)
        def right(top: int) -> int:
            return top * 3

        @asset(registry=registry)
        def bottom(left: int, right: int) -> int:
            return left + right

        graph = DependencyGraph.from_registry(registry)

        upstream = graph.get_all_upstream(AssetKey(name="bottom"))
        assert upstream == {
            AssetKey(name="top"),
            AssetKey(name="left"),
            AssetKey(name="right"),
        }
