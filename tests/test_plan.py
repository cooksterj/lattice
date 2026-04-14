"""Tests for ExecutionPlan."""

import pytest
from pydantic import ValidationError

from lattice import AssetKey, AssetRegistry, ExecutionPlan, asset


class TestExecutionPlanResolve:
    """Tests for ExecutionPlan.resolve()."""

    def test_empty_registry(self, registry: AssetRegistry) -> None:
        """Empty registry produces empty plan."""
        plan = ExecutionPlan.resolve(registry)
        assert len(plan) == 0
        assert list(plan) == []

    def test_single_asset(self, registry: AssetRegistry) -> None:
        """Single asset produces single-element plan."""

        @asset(registry=registry)
        def only() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        assert len(plan) == 1
        assert plan.assets[0].key == AssetKey(name="only")

    def test_linear_chain_full(self, registry: AssetRegistry) -> None:
        """Full plan includes all assets in order."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        plan = ExecutionPlan.resolve(registry)
        keys = [a.key for a in plan]

        assert len(keys) == 3
        assert keys.index(AssetKey(name="a")) < keys.index(AssetKey(name="b"))
        assert keys.index(AssetKey(name="b")) < keys.index(AssetKey(name="c"))

    def test_resolve_with_target_string(self, registry: AssetRegistry) -> None:
        """Resolve with string target filters to required assets."""

        @asset(registry=registry)
        def source() -> int:
            return 1

        @asset(registry=registry, deps=["source"])
        def target(source: int) -> int:
            return source + 1

        @asset(registry=registry)
        def unrelated() -> int:
            return 99

        plan = ExecutionPlan.resolve(registry, target="target")

        assert len(plan) == 2
        assert "source" in plan
        assert "target" in plan
        assert "unrelated" not in plan
        assert plan.target == AssetKey(name="target")

    def test_resolve_with_target_asset_key(self, registry: AssetRegistry) -> None:
        """Resolve with AssetKey target."""

        @asset(registry=registry)
        def dep() -> int:
            return 1

        @asset(registry=registry, deps=["dep"])
        def main(dep: int) -> int:
            return dep * 2

        target_key = AssetKey(name="main")
        plan = ExecutionPlan.resolve(registry, target=target_key)

        assert len(plan) == 2
        assert plan.target == target_key

    def test_resolve_target_not_found(self, registry: AssetRegistry) -> None:
        """Resolve with nonexistent target raises KeyError."""

        @asset(registry=registry)
        def exists() -> int:
            return 1

        with pytest.raises(KeyError, match="nonexistent"):
            ExecutionPlan.resolve(registry, target="nonexistent")

    def test_diamond_dependency_plan(self, registry: AssetRegistry) -> None:
        """Diamond pattern resolves correctly."""

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

        plan = ExecutionPlan.resolve(registry, target="leaf")
        keys = [a.key for a in plan]

        assert len(keys) == 4
        # Root must be first
        assert keys[0] == AssetKey(name="root")
        # Leaf must be last
        assert keys[-1] == AssetKey(name="leaf")

    def test_target_with_no_deps(self, registry: AssetRegistry) -> None:
        """Target with no dependencies produces single-element plan."""

        @asset(registry=registry)
        def standalone() -> int:
            return 42

        @asset(registry=registry)
        def other() -> int:
            return 99

        plan = ExecutionPlan.resolve(registry, target="standalone")

        assert len(plan) == 1
        assert plan.assets[0].key == AssetKey(name="standalone")


class TestExecutionPlanProtocols:
    """Tests for ExecutionPlan iteration and containment."""

    def test_iter(self, registry: AssetRegistry) -> None:
        """Plan is iterable."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        plan = ExecutionPlan.resolve(registry)

        assets = list(plan)
        assert len(assets) == 2
        assert all(hasattr(a, "key") for a in assets)

    def test_len(self, registry: AssetRegistry) -> None:
        """Plan has correct length."""

        @asset(registry=registry)
        def x() -> int:
            return 1

        @asset(registry=registry)
        def y() -> int:
            return 2

        @asset(registry=registry)
        def z() -> int:
            return 3

        plan = ExecutionPlan.resolve(registry)
        assert len(plan) == 3

    def test_contains_with_string(self, registry: AssetRegistry) -> None:
        """Plan supports 'in' operator with string."""

        @asset(registry=registry)
        def included() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)

        assert "included" in plan
        assert "not_included" not in plan

    def test_contains_with_asset_key(self, registry: AssetRegistry) -> None:
        """Plan supports 'in' operator with AssetKey."""

        @asset(registry=registry)
        def present() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)

        assert AssetKey(name="present") in plan
        assert AssetKey(name="absent") not in plan


class TestExecutionPlanImmutability:
    """Tests for ExecutionPlan immutability."""

    def test_frozen_model(self, registry: AssetRegistry) -> None:
        """Plan is immutable (frozen)."""

        @asset(registry=registry)
        def test_asset() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)

        with pytest.raises(ValidationError):
            plan.target = AssetKey(name="other")  # type: ignore[misc]


class TestExecutionPlanDownstream:
    """Tests for ExecutionPlan.resolve() with include_downstream=True."""

    def test_simple_chain_from_root(self, registry: AssetRegistry) -> None:
        """A->B->C chain, target=A with downstream runs all three."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        plan = ExecutionPlan.resolve(registry, target="a", include_downstream=True)

        assert len(plan) == 3
        assert "a" in plan
        assert "b" in plan
        assert "c" in plan
        assert plan.target == AssetKey(name="a")

    def test_simple_chain_from_middle(self, registry: AssetRegistry) -> None:
        """A->B->C, target=B runs B+C only (not A)."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry, deps=["b"])
        def c(b: int) -> int:
            return b + 1

        plan = ExecutionPlan.resolve(registry, target="b", include_downstream=True)

        assert len(plan) == 2
        assert "b" in plan
        assert "c" in plan
        assert "a" not in plan
        assert plan.target == AssetKey(name="b")

    def test_diamond_from_fork_point(self, registry: AssetRegistry) -> None:
        """Diamond pattern, target=root with downstream runs all four."""

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

        plan = ExecutionPlan.resolve(registry, target="root", include_downstream=True)

        assert len(plan) == 4
        assert "root" in plan
        assert "left" in plan
        assert "right" in plan
        assert "leaf" in plan
        assert plan.target == AssetKey(name="root")

    def test_diamond_from_one_branch(self, registry: AssetRegistry) -> None:
        """Diamond pattern, target=left runs left+leaf (not root or right)."""

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

        plan = ExecutionPlan.resolve(registry, target="left", include_downstream=True)

        assert len(plan) == 2
        assert "left" in plan
        assert "leaf" in plan
        assert "root" not in plan
        assert "right" not in plan
        assert plan.target == AssetKey(name="left")

    def test_cross_group_downstream(self, registry: AssetRegistry) -> None:
        """Asset in 'dbt' group triggers dependent in 'analytics' group."""

        @asset(registry=registry, key=AssetKey(name="model_x", group="dbt"))
        def model_x() -> int:
            return 1

        @asset(
            registry=registry,
            key=AssetKey(name="report", group="analytics"),
            deps=[AssetKey(name="model_x", group="dbt")],
        )
        def report(model_x: int) -> int:
            return model_x + 1

        plan = ExecutionPlan.resolve(registry, target="dbt/model_x", include_downstream=True)

        assert len(plan) == 2
        assert "dbt/model_x" in plan
        assert "analytics/report" in plan
        assert plan.target == AssetKey(name="model_x", group="dbt")

    def test_intra_group_partial(self, registry: AssetRegistry) -> None:
        """Two independent chains in 'dbt' group; target selects only one chain."""

        @asset(registry=registry, key=AssetKey(name="stg_orders", group="dbt"))
        def stg_orders() -> int:
            return 1

        @asset(
            registry=registry,
            key=AssetKey(name="fct_orders", group="dbt"),
            deps=[AssetKey(name="stg_orders", group="dbt")],
        )
        def fct_orders(stg_orders: int) -> int:
            return stg_orders + 1

        @asset(registry=registry, key=AssetKey(name="stg_customers", group="dbt"))
        def stg_customers() -> int:
            return 1

        @asset(
            registry=registry,
            key=AssetKey(name="dim_customers", group="dbt"),
            deps=[AssetKey(name="stg_customers", group="dbt")],
        )
        def dim_customers(stg_customers: int) -> int:
            return stg_customers + 1

        plan = ExecutionPlan.resolve(registry, target="dbt/stg_orders", include_downstream=True)

        assert len(plan) == 2
        assert "dbt/stg_orders" in plan
        assert "dbt/fct_orders" in plan
        assert "dbt/stg_customers" not in plan
        assert "dbt/dim_customers" not in plan
        assert plan.target == AssetKey(name="stg_orders", group="dbt")

    def test_no_downstream(self, registry: AssetRegistry) -> None:
        """Leaf node with no dependents runs only itself."""

        @asset(registry=registry)
        def root() -> int:
            return 1

        @asset(registry=registry, deps=["root"])
        def leaf(root: int) -> int:
            return root + 1

        plan = ExecutionPlan.resolve(registry, target="leaf", include_downstream=True)

        assert len(plan) == 1
        assert "leaf" in plan
        assert "root" not in plan
        assert plan.target == AssetKey(name="leaf")

    def test_downstream_with_unrelated_assets(self, registry: AssetRegistry) -> None:
        """A->B chain plus unrelated C; target=A runs A+B only, not C."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 1

        @asset(registry=registry)
        def c() -> int:
            return 99

        plan = ExecutionPlan.resolve(registry, target="a", include_downstream=True)

        assert len(plan) == 2
        assert "a" in plan
        assert "b" in plan
        assert "c" not in plan
        assert plan.target == AssetKey(name="a")
