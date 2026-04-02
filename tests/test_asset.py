"""Tests for the @asset decorator and core models."""

import pytest

from lattice import (
    AssetKey,
    AssetRegistry,
    AssetWithChecks,
    ExecutionPlan,
    asset,
    get_global_registry,
)
from lattice.executor import AssetStatus, AsyncExecutor, Executor
from lattice.io import MemoryIOManager


class TestAssetKey:
    """Tests for AssetKey model."""

    def test_create_with_name_only(self) -> None:
        key = AssetKey(name="my_asset")
        assert key.name == "my_asset"
        assert key.group == "default"

    def test_create_with_group(self) -> None:
        key = AssetKey(name="stats", group="analytics")
        assert key.name == "stats"
        assert key.group == "analytics"

    def test_string_representation_default_group(self) -> None:
        key = AssetKey(name="my_asset")
        assert str(key) == "my_asset"

    def test_string_representation_custom_group(self) -> None:
        key = AssetKey(name="stats", group="analytics")
        assert str(key) == "analytics/stats"

    def test_immutable(self) -> None:
        from pydantic import ValidationError

        key = AssetKey(name="my_asset")
        with pytest.raises(ValidationError):
            key.name = "other"  # type: ignore[misc]

    def test_hashable(self) -> None:
        key1 = AssetKey(name="my_asset")
        key2 = AssetKey(name="my_asset")
        assert hash(key1) == hash(key2)
        assert {key1, key2} == {key1}

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            AssetKey(name="")


class TestAssetDecorator:
    """Tests for the @asset decorator."""

    def test_basic_decoration(self) -> None:
        @asset
        def my_asset() -> int:
            return 42

        # @asset returns AssetWithChecks which wraps AssetDefinition
        assert isinstance(my_asset, AssetWithChecks)
        assert my_asset.key == AssetKey(name="my_asset")
        assert my_asset() == 42

    def test_with_explicit_key(self) -> None:
        @asset(key=AssetKey(name="custom_name", group="custom_group"))
        def my_asset() -> int:
            return 42

        assert my_asset.key.name == "custom_name"
        assert my_asset.key.group == "custom_group"

    def test_dependency_extraction(self) -> None:
        @asset
        def source_a() -> int:
            return 1

        @asset
        def source_b() -> int:
            return 2

        @asset(deps=["source_a", "source_b"])
        def combined(source_a: int, source_b: int) -> int:
            return source_a + source_b

        assert combined.dependencies == (
            AssetKey(name="source_a"),
            AssetKey(name="source_b"),
        )

    def test_explicit_deps_for_grouped_assets(self) -> None:
        """Test that deps parameter allows explicit dependency specification."""

        @asset(
            key=AssetKey(name="dashboard", group="analytics"),
            deps=[
                AssetKey(name="daily_revenue", group="analytics"),
                AssetKey(name="user_stats", group="analytics"),
            ],
        )
        def dashboard(revenue: dict, stats: dict) -> dict:
            return {"revenue": revenue, "stats": stats}

        assert dashboard.dependencies == (
            AssetKey(name="daily_revenue", group="analytics"),
            AssetKey(name="user_stats", group="analytics"),
        )
        assert dashboard.key == AssetKey(name="dashboard", group="analytics")

    def test_mixed_string_and_asset_key_deps(self) -> None:
        """Test that deps can mix strings and AssetKey objects."""

        @asset(
            deps=["regular_dep", AssetKey(name="source", group="data")],
        )
        def mixed_deps(regular_dep: int, grouped_dep: int) -> int:
            return regular_dep + grouped_dep

        assert mixed_deps.dependencies == (
            AssetKey(name="regular_dep"),
            AssetKey(name="source", group="data"),
        )

    def test_arity_mismatch_raises(self) -> None:
        """Declaring wrong number of deps raises TypeError."""
        with pytest.raises(TypeError, match="declares 2 dependency"):

            @asset(deps=["a", "b"])
            def bad(x: int) -> int:
                return x

    def test_return_type_extraction(self) -> None:
        @asset
        def typed_asset() -> dict[str, int]:
            return {"count": 1}

        assert typed_asset.return_type == dict[str, int]

    def test_description_from_docstring(self) -> None:
        @asset
        def documented_asset() -> int:
            """This is my asset description."""
            return 42

        assert documented_asset.description == "This is my asset description."

    def test_explicit_description(self) -> None:
        @asset(description="Explicit description")
        def my_asset() -> int:
            """Docstring here."""
            return 42

        assert my_asset.description == "Explicit description"

    def test_registers_to_global_registry(self) -> None:
        @asset
        def auto_registered() -> int:
            return 1

        registry = get_global_registry()
        assert "auto_registered" in registry
        # Registry stores AssetDefinition, decorator returns AssetWithChecks
        retrieved = registry.get("auto_registered")
        assert retrieved.key == auto_registered.key

    def test_registers_to_custom_registry(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def custom_registered() -> int:
            return 1

        assert "custom_registered" in registry
        assert "custom_registered" not in get_global_registry()


class TestAssetRegistry:
    """Tests for AssetRegistry."""

    def test_register_and_get(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        # Registry stores AssetDefinition, decorator returns AssetWithChecks
        retrieved = registry.get("my_asset")
        assert retrieved.key == my_asset.key

    def test_get_with_asset_key(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        key = AssetKey(name="my_asset")
        retrieved = registry.get(key)
        assert retrieved.key == my_asset.key

    def test_duplicate_registration_raises(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 1

        with pytest.raises(ValueError, match="already registered"):

            @asset(registry=registry)
            def my_asset() -> int:  # noqa: F811
                return 2

    def test_get_missing_raises(self, registry: AssetRegistry) -> None:
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_iteration(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def asset_a() -> int:
            return 1

        @asset(registry=registry)
        def asset_b() -> int:
            return 2

        assets = list(registry)
        assert len(assets) == 2

    def test_len(self, registry: AssetRegistry) -> None:
        assert len(registry) == 0

        @asset(registry=registry)
        def my_asset() -> int:
            return 1

        assert len(registry) == 1


class TestWrapperMetadata:
    """Tests for _create_async_wrapper and _create_sync_wrapper metadata preservation."""

    def test_sync_wrapper_preserves_name(self) -> None:
        """Sync wrapper preserves __name__."""
        from lattice.asset.helpers import _create_sync_wrapper

        def my_function() -> int:
            return 42

        wrapped = _create_sync_wrapper(my_function)
        assert wrapped.__name__ == "my_function"

    def test_sync_wrapper_preserves_doc(self) -> None:
        """Sync wrapper preserves __doc__."""
        from lattice.asset.helpers import _create_sync_wrapper

        def my_function() -> int:
            """My docstring."""
            return 42

        wrapped = _create_sync_wrapper(my_function)
        assert wrapped.__doc__ == "My docstring."

    def test_sync_wrapper_delegates_correctly(self) -> None:
        """Sync wrapper calls through to the original function."""
        from lattice.asset.helpers import _create_sync_wrapper

        def add(a: int, b: int) -> int:
            return a + b

        wrapped = _create_sync_wrapper(add)
        assert wrapped(3, 4) == 7

    def test_async_wrapper_preserves_name(self) -> None:
        """Async wrapper preserves __name__."""
        from lattice.asset.helpers import _create_async_wrapper

        async def my_async_fn() -> int:
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert wrapped.__name__ == "my_async_fn"

    def test_async_wrapper_preserves_doc(self) -> None:
        """Async wrapper preserves __doc__."""
        from lattice.asset.helpers import _create_async_wrapper

        async def my_async_fn() -> int:
            """Async docstring."""
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert wrapped.__doc__ == "Async docstring."

    def test_async_wrapper_returns_coroutine_function(self) -> None:
        """Async wrapper is recognized as a coroutine function."""
        import inspect

        from lattice.asset.helpers import _create_async_wrapper

        async def my_async_fn() -> int:
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert inspect.iscoroutinefunction(wrapped)


class TestAssetDecoratorFunction:
    """Tests for the _asset_decorator extracted function."""

    def test_produces_correct_asset_with_checks(self, registry: AssetRegistry) -> None:
        """_asset_decorator creates an AssetWithChecks with correct attributes."""
        from lattice.asset.asset import _asset_decorator
        from lattice.observability.checks import AssetWithChecks

        def my_func() -> int:
            """My description."""
            return 42

        result = _asset_decorator(my_func, None, None, None, registry)

        assert isinstance(result, AssetWithChecks)
        assert result.key == AssetKey(name="my_func")
        assert result.description == "My description."
        assert "my_func" in registry

    def test_explicit_key_and_description(self, registry: AssetRegistry) -> None:
        """_asset_decorator respects explicit key and description."""
        from lattice.asset.asset import _asset_decorator

        def my_func() -> int:
            return 42

        key = AssetKey(name="custom", group="grp")
        result = _asset_decorator(my_func, key, None, "Explicit desc", registry)

        assert result.key == key
        assert result.description == "Explicit desc"


class TestStringShorthandDeps:
    """Tests for string shorthand in deps parameter."""

    def test_string_shorthand_produces_default_group_asset_key(self) -> None:
        """deps=['raw_users'] produces AssetKey(name='raw_users', group='default')."""

        @asset(deps=["raw_users"])
        def cleaned(raw_users: str) -> str:
            return raw_users

        assert cleaned.dependencies == (AssetKey(name="raw_users"),)
        assert cleaned.dependencies[0].group == "default"

    def test_mixed_strings_and_asset_keys(self) -> None:
        """deps can mix string shorthand and explicit AssetKey objects."""

        @asset(
            deps=["source", AssetKey(name="config", group="analytics")],
        )
        def combined(source: int, config: dict) -> dict:
            return {"source": source, "config": config}

        assert combined.dependencies == (
            AssetKey(name="source"),
            AssetKey(name="config", group="analytics"),
        )
        assert combined.dependencies[0].group == "default"
        assert combined.dependencies[1].group == "analytics"

    def test_empty_deps_list_produces_zero_dependencies(self) -> None:
        """deps=[] explicitly declares zero dependencies."""

        @asset(deps=[])
        def my_asset() -> int:
            return 42

        assert my_asset.dependencies == ()
        assert len(my_asset.dependencies) == 0


class TestArityMismatch:
    """Tests for arity mismatch between deps and function parameters."""

    def test_more_deps_than_params_raises(self) -> None:
        """2 deps but 1 param raises TypeError at decoration time."""
        with pytest.raises(TypeError, match="declares 2 dependency"):

            @asset(deps=["a", "b"])
            def bad(x: int) -> int:
                return x

    def test_more_params_than_deps_raises(self) -> None:
        """2 deps but 3 params raises TypeError at decoration time."""
        with pytest.raises(TypeError, match="declares 2 dependency"):

            @asset(deps=["a", "b"])
            def bad(x: int, y: int, z: int) -> int:
                return x + y + z

    def test_three_deps_two_params_raises(self) -> None:
        """3 deps but 2 params raises TypeError at decoration time."""
        with pytest.raises(TypeError, match="declares 3 dependency"):

            @asset(deps=["a", "b", "c"])
            def bad(x: int, y: int) -> int:
                return x + y


class TestSourceAssetNoImplicitDeps:
    """Tests that omitting deps produces a source asset with zero dependencies."""

    def test_source_asset_with_params_has_no_deps(self) -> None:
        """@asset on a function with params but no deps has zero dependencies."""

        @asset
        def my_asset(x: int) -> int:
            return x

        assert my_asset.dependencies == ()
        assert len(my_asset.dependencies) == 0

    def test_source_asset_no_params_has_no_deps(self) -> None:
        """@asset on a function with no params has zero dependencies."""

        @asset
        def my_asset() -> int:
            return 42

        assert my_asset.dependencies == ()


class TestSkipParamsArityCheck:
    """Tests that SKIP_PARAMS (partition_key, context) are excluded from arity validation."""

    def test_partition_key_excluded_from_arity_check(self) -> None:
        """partition_key param is not counted for arity matching."""

        @asset(deps=["source"])
        def my_asset(data: int, partition_key: str) -> int:
            return data

        assert my_asset.dependencies == (AssetKey(name="source"),)

    def test_context_excluded_from_arity_check(self) -> None:
        """context param is not counted for arity matching."""

        @asset(deps=["source"])
        def my_asset(data: int, context: dict) -> int:
            return data

        assert my_asset.dependencies == (AssetKey(name="source"),)

    def test_both_skip_params_excluded(self) -> None:
        """Both partition_key and context are excluded from arity check."""

        @asset(deps=["source"])
        def my_asset(data: int, partition_key: str, context: dict) -> int:
            return data

        assert my_asset.dependencies == (AssetKey(name="source"),)


class TestPositionalInjection:
    """Tests for LAT-9 positional injection: deps[i] maps to param[i]."""

    def test_first_dep_maps_to_first_param(self, registry: AssetRegistry) -> None:
        """deps[0] value is injected into the first function parameter."""

        @asset(registry=registry)
        def alpha() -> str:
            return "ALPHA"

        @asset(registry=registry)
        def beta() -> str:
            return "BETA"

        @asset(registry=registry, deps=["alpha", "beta"])
        def consumer(x: str, y: str) -> str:
            return f"{x}+{y}"

        plan = ExecutionPlan.resolve(registry, target="consumer")
        io = MemoryIOManager()
        Executor(io_manager=io).execute(plan)

        assert io.load(AssetKey(name="consumer")) == "ALPHA+BETA"

    def test_reversed_deps_order(self, registry: AssetRegistry) -> None:
        """Reversing deps order reverses which param gets which value."""

        @asset(registry=registry)
        def first() -> int:
            return 1

        @asset(registry=registry)
        def second() -> int:
            return 2

        @asset(registry=registry, deps=["second", "first"])
        def result(a: int, b: int) -> tuple:
            return (a, b)

        plan = ExecutionPlan.resolve(registry, target="result")
        io = MemoryIOManager()
        Executor(io_manager=io).execute(plan)

        # a gets "second" (2), b gets "first" (1)
        assert io.load(AssetKey(name="result")) == (2, 1)

    def test_grouped_deps_positional(self, registry: AssetRegistry) -> None:
        """Grouped AssetKey deps are injected by position, not name."""

        @asset(registry=registry, group="analytics")
        def rev() -> float:
            return 100.0

        @asset(registry=registry, group="analytics")
        def count() -> int:
            return 5

        @asset(
            registry=registry,
            deps=[
                AssetKey(name="count", group="analytics"),
                AssetKey(name="rev", group="analytics"),
            ],
        )
        def report(n: int, total: float) -> str:
            return f"{n} items, ${total}"

        plan = ExecutionPlan.resolve(registry, target="report")
        io = MemoryIOManager()
        Executor(io_manager=io).execute(plan)

        assert io.load(AssetKey(name="report")) == "5 items, $100.0"

    @pytest.mark.asyncio
    async def test_positional_injection_async_executor(self, registry: AssetRegistry) -> None:
        """Positional injection works correctly with AsyncExecutor."""

        @asset(registry=registry)
        async def src_a() -> int:
            return 10

        @asset(registry=registry)
        async def src_b() -> int:
            return 20

        @asset(registry=registry, deps=["src_b", "src_a"])
        async def combined(first: int, second: int) -> int:
            return first - second

        plan = ExecutionPlan.resolve(registry, target="combined")
        io = MemoryIOManager()
        await AsyncExecutor(io_manager=io).execute(plan)

        # first = src_b (20), second = src_a (10)
        assert io.load(AssetKey(name="combined")) == 10


class TestMultiLevelDagExecution:
    """End-to-end tests for multi-level DAG with deps-only declarations."""

    def test_five_level_dag_sync(self, registry: AssetRegistry) -> None:
        """Multi-level DAG executes correctly with sync Executor."""

        @asset(registry=registry)
        def raw_a() -> int:
            return 1

        @asset(registry=registry)
        def raw_b() -> int:
            return 2

        @asset(registry=registry, deps=["raw_a"])
        def clean_a(val: int) -> int:
            return val * 10

        @asset(registry=registry, deps=["raw_a", "raw_b"])
        def joined(x: int, y: int) -> int:
            return x + y

        @asset(registry=registry, deps=["clean_a", "joined"])
        def final(left: int, right: int) -> int:
            return left + right

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 5
        assert io.load(AssetKey(name="raw_a")) == 1
        assert io.load(AssetKey(name="raw_b")) == 2
        assert io.load(AssetKey(name="clean_a")) == 10
        assert io.load(AssetKey(name="joined")) == 3
        assert io.load(AssetKey(name="final")) == 13

    @pytest.mark.asyncio
    async def test_five_level_dag_async(self, registry: AssetRegistry) -> None:
        """Multi-level DAG executes correctly with AsyncExecutor."""

        @asset(registry=registry)
        async def raw_x() -> int:
            return 5

        @asset(registry=registry)
        async def raw_y() -> int:
            return 3

        @asset(registry=registry, deps=["raw_x"])
        async def mid_x(val: int) -> int:
            return val * 2

        @asset(registry=registry, deps=["raw_x", "raw_y"])
        async def mid_y(a: int, b: int) -> int:
            return a - b

        @asset(registry=registry, deps=["mid_x", "mid_y"])
        async def bottom(left: int, right: int) -> int:
            return left * right

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 5
        assert io.load(AssetKey(name="mid_x")) == 10
        assert io.load(AssetKey(name="mid_y")) == 2
        assert io.load(AssetKey(name="bottom")) == 20


class TestGroupShorthand:
    """Tests for the group shorthand parameter on @asset."""

    def test_group_shorthand_creates_correct_key(self) -> None:
        """@asset(group='analytics') derives name from function, sets group."""

        @asset(group="analytics")
        def daily_revenue() -> dict:
            return {"revenue": 100}

        assert daily_revenue.key == AssetKey(name="daily_revenue", group="analytics")
        assert daily_revenue.key.name == "daily_revenue"
        assert daily_revenue.key.group == "analytics"

    def test_group_shorthand_with_deps(self) -> None:
        """group shorthand works with deps parameter."""

        @asset(group="analytics", deps=["source"])
        def report(source: int) -> str:
            return f"report: {source}"

        assert report.key == AssetKey(name="report", group="analytics")
        assert report.dependencies == (AssetKey(name="source"),)

    def test_group_shorthand_with_description(self) -> None:
        """group shorthand works with description parameter."""

        @asset(group="analytics", description="Custom description")
        def my_asset() -> int:
            """Docstring."""
            return 42

        assert my_asset.key.group == "analytics"
        assert my_asset.description == "Custom description"

    def test_group_shorthand_with_registry(self, registry: AssetRegistry) -> None:
        """group shorthand works with custom registry."""

        @asset(group="analytics", registry=registry)
        def custom_asset() -> int:
            return 1

        assert "custom_asset" not in get_global_registry()
        assert custom_asset.key == AssetKey(name="custom_asset", group="analytics")
        retrieved = registry.get(AssetKey(name="custom_asset", group="analytics"))
        assert retrieved.key == custom_asset.key

    def test_group_default_is_default(self) -> None:
        """@asset(group='default') produces same key as bare @asset."""

        @asset(group="default")
        def my_asset() -> int:
            return 1

        expected = AssetKey(name="my_asset", group="default")
        assert my_asset.key == expected
        assert my_asset.key.group == "default"


class TestGroupKeyMutualExclusion:
    """Tests that key and group cannot be combined."""

    def test_group_and_key_raises_value_error(self) -> None:
        """Specifying both key and group raises ValueError."""
        with pytest.raises(ValueError, match="Cannot specify both"):

            @asset(key=AssetKey(name="x", group="y"), group="z")
            def my_asset() -> int:
                return 42

    def test_error_message_mentions_key_and_group(self) -> None:
        """Error message is clear about the conflict."""
        with pytest.raises(ValueError, match="'key'.*'group'"):

            @asset(key=AssetKey(name="a"), group="b")
            def my_asset() -> int:
                return 1


class TestGroupDefaultBehavior:
    """Tests that default behavior is preserved when group is not specified."""

    def test_no_group_no_key_defaults(self) -> None:
        """Bare @asset produces default group."""

        @asset
        def plain_asset() -> int:
            return 1

        assert plain_asset.key == AssetKey(name="plain_asset")
        assert plain_asset.key.group == "default"

    def test_key_still_works_alone(self) -> None:
        """Explicit key= without group still works."""

        @asset(key=AssetKey(name="custom", group="grp"))
        def my_asset() -> int:
            return 42

        assert my_asset.key == AssetKey(name="custom", group="grp")


class TestGroupEndToEnd:
    """End-to-end tests for group shorthand in execution pipeline."""

    def test_grouped_asset_executes_correctly(self, registry: AssetRegistry) -> None:
        """Assets defined with group= execute and produce correct results."""

        @asset(registry=registry)
        def source() -> int:
            return 10

        @asset(registry=registry, group="analytics", deps=["source"])
        def doubled(source: int) -> int:
            return source * 2

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 2
        assert io.load(AssetKey(name="doubled", group="analytics")) == 20

    def test_grouped_asset_in_dependency_graph(self, registry: AssetRegistry) -> None:
        """Grouped assets appear correctly in DependencyGraph."""
        from lattice.graph import DependencyGraph

        @asset(registry=registry, group="data")
        def raw() -> int:
            return 1

        @asset(registry=registry, group="analytics", deps=[AssetKey(name="raw", group="data")])
        def processed(raw: int) -> int:
            return raw + 1

        graph = DependencyGraph.from_registry(registry)
        raw_key = AssetKey(name="raw", group="data")
        proc_key = AssetKey(name="processed", group="analytics")

        assert raw_key in graph.adjacency
        assert proc_key in graph.adjacency
        assert raw_key in graph.adjacency[proc_key]

    @pytest.mark.asyncio
    async def test_grouped_asset_async_execution(self, registry: AssetRegistry) -> None:
        """Async execution works with group shorthand."""
        from lattice.executor import AsyncExecutor

        @asset(registry=registry, group="metrics")
        async def counter() -> int:
            return 42

        @asset(registry=registry, deps=[AssetKey(name="counter", group="metrics")])
        async def display(counter: int) -> str:
            return f"count={counter}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="display")) == "count=42"


class TestWebDemoIntegration:
    """Integration test: verify the migrated web_demo builds a valid graph."""

    def test_web_demo_graph_and_execution(self) -> None:
        """web_demo.py assets form a valid DAG and execute without error."""
        import importlib
        import logging
        import sys

        import lattice.logging.config as log_config
        from lattice.graph import DependencyGraph

        # Save logger state — web_demo calls configure_logging() at import,
        # which sets propagate=0 on sub-loggers via logging.conf.
        logger_names = ["lattice", "lattice.executor", "lattice.web"]
        saved_state: dict[str, tuple] = {}
        for name in logger_names:
            lgr = logging.getLogger(name)
            saved_state[name] = (lgr.handlers[:], lgr.level, lgr.propagate)
        saved_configured = log_config._configured

        # We need to temporarily redirect asset registration to our test registry.
        # The demo registers to global, so we'll use global and clean up.
        from lattice import get_global_registry

        global_reg = get_global_registry()
        global_reg.clear()

        try:
            # Import the demo (this triggers @asset registrations)
            spec = importlib.util.find_spec("examples.web_demo")
            if spec is None:
                pytest.skip("examples.web_demo not importable")

            # Clear any prior modules to force fresh registration
            for key in list(sys.modules.keys()):
                if key.startswith("examples.web_demo"):
                    del sys.modules[key]

            importlib.import_module("examples.web_demo")

            # Verify we have registered assets
            asset_count = len(global_reg)
            assert asset_count >= 14, f"Expected >= 14 assets, got {asset_count}"

            # Build graph — should not raise CyclicDependencyError
            graph = DependencyGraph.from_registry(global_reg)

            # Topological sort should succeed
            sorted_keys = graph.topological_sort()
            assert len(sorted_keys) == asset_count

            # Verify no cycles
            cycles = graph.detect_cycles()
            assert cycles is None

            # Execute the full DAG
            plan = ExecutionPlan.resolve(global_reg)
            io = MemoryIOManager()
            result = Executor(io_manager=io).execute(plan)

            assert result.status == AssetStatus.COMPLETED
            assert result.completed_count == asset_count
            assert result.failed_count == 0

            # Verify the executive_dashboard exists in results
            dashboard_key = AssetKey(name="executive_dashboard", group="analytics")
            assert io.has(dashboard_key)
        finally:
            # Restore logger state and clean up
            global_reg.clear()
            for name in logger_names:
                lgr = logging.getLogger(name)
                lgr.handlers = saved_state[name][0]
                lgr.setLevel(saved_state[name][1])
                lgr.propagate = saved_state[name][2]
            log_config._configured = saved_configured
            # Remove demo module to avoid polluting other tests
            for key in list(sys.modules.keys()):
                if key.startswith("examples"):
                    del sys.modules[key]
